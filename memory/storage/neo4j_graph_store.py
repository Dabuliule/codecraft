"""Neo4j 图存储层：用于 SemanticMemory 的知识图谱持久化。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError


@dataclass
class Entity:
    """实体节点模型。"""

    entity_id: str
    name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SemanticFact:
    """事实节点模型。"""

    fact_id: str
    content: str
    user_id: str
    importance: float
    confidence: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GraphStoreError(Exception):
    """图存储基类异常。"""


class NodeNotFoundError(GraphStoreError):
    """节点不存在异常。"""


class InvalidRelationTypeError(GraphStoreError):
    """关系类型非法异常。"""


class Neo4jGraphStore:
    """Neo4j 图存储实现，封装会话生命周期与 Cypher 访问。"""

    # 统一管理核心 Cypher，避免业务代码分散拼接。
    _QUERY_CREATE_ENTITY_CONSTRAINT = (
        "CREATE CONSTRAINT entity_entity_id_unique IF NOT EXISTS "
        "FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE"
    )
    _QUERY_CREATE_FACT_CONSTRAINT = (
        "CREATE CONSTRAINT fact_fact_id_unique IF NOT EXISTS "
        "FOR (f:Fact) REQUIRE f.fact_id IS UNIQUE"
    )
    _QUERY_CREATE_ENTITY_NAME_INDEX = " ".join(
        ["CREATE", "INDEX", "entity_name_idx", "IF", "NOT", "EXISTS", "FOR", "(e:Entity)", "ON", "(e.name)"]
    )
    _QUERY_CREATE_ENTITY_TYPE_INDEX = " ".join(
        [
            "CREATE",
            "INDEX",
            "entity_type_idx",
            "IF",
            "NOT",
            "EXISTS",
            "FOR",
            "(e:Entity)",
            "ON",
            "(e.entity_type)",
        ]
    )
    _QUERY_CREATE_FACT_USER_INDEX = " ".join(
        ["CREATE", "INDEX", "fact_user_idx", "IF", "NOT", "EXISTS", "FOR", "(f:Fact)", "ON", "(f.user_id)"]
    )
    _QUERY_CREATE_FACT_CREATED_AT_INDEX = " ".join(
        [
            "CREATE",
            "INDEX",
            "fact_created_at_idx",
            "IF",
            "NOT",
            "EXISTS",
            "FOR",
            "(f:Fact)",
            "ON",
            "(f.created_at)",
        ]
    )

    _SCHEMA_QUERIES: tuple[str, ...] = (
        _QUERY_CREATE_ENTITY_CONSTRAINT,
        _QUERY_CREATE_FACT_CONSTRAINT,
        _QUERY_CREATE_ENTITY_NAME_INDEX,
        _QUERY_CREATE_ENTITY_TYPE_INDEX,
        _QUERY_CREATE_FACT_USER_INDEX,
        _QUERY_CREATE_FACT_CREATED_AT_INDEX,
    )

    _QUERY_UPSERT_ENTITY = """
    MERGE (e:Entity {entity_id: $entity_id})
    ON CREATE SET
        e.name = $name,
        e.entity_type = $entity_type,
        e.aliases = $aliases,
        e.created_at = $created_at,
        e.updated_at = $updated_at
    ON MATCH SET
        e.name = $name,
        e.entity_type = $entity_type,
        e.aliases = $aliases,
        e.updated_at = $updated_at
    RETURN e.entity_id AS entity_id
    """

    _QUERY_UPSERT_FACT = """
    MERGE (f:Fact {fact_id: $fact_id})
    ON CREATE SET
        f.content = $content,
        f.user_id = $user_id,
        f.importance = $importance,
        f.confidence = $confidence,
        f.created_at = $created_at,
        f.updated_at = $updated_at
    ON MATCH SET
        f.content = $content,
        f.user_id = $user_id,
        f.importance = $importance,
        f.confidence = $confidence,
        f.updated_at = $updated_at
    RETURN f.fact_id AS fact_id
    """

    _QUERY_CHECK_ENTITY_EXISTS = """
    MATCH (e:Entity {entity_id: $entity_id})
    RETURN e.entity_id AS entity_id
    LIMIT 1
    """

    _QUERY_CHECK_FACT_EXISTS = """
    MATCH (f:Fact {fact_id: $fact_id})
    RETURN f.fact_id AS fact_id
    LIMIT 1
    """

    _QUERY_LINK_FACT_MENTIONS_ENTITY = """
    MATCH (f:Fact {fact_id: $fact_id})
    MATCH (e:Entity {entity_id: $entity_id})
    MERGE (f)-[r:MENTIONS]->(e)
    ON CREATE SET r.created_at = $now, r.updated_at = $now
    ON MATCH SET r.updated_at = $now
    RETURN type(r) AS relation_type
    """

    _QUERY_LINK_ENTITY_RELATED_TO = """
    MATCH (s:Entity {entity_id: $source_entity_id})
    MATCH (t:Entity {entity_id: $target_entity_id})
    MERGE (s)-[r:RELATED_TO]->(t)
    ON CREATE SET r.created_at = $now
    SET r.updated_at = $now, r.weight = $weight
    RETURN type(r) AS relation_type
    """

    _QUERY_MARK_SUPERSEDED = """
    MATCH (old:Fact {fact_id: $old_fact_id})
    MATCH (new:Fact {fact_id: $new_fact_id})
    MERGE (old)-[r:SUPERSEDED_BY]->(new)
    ON CREATE SET r.created_at = $now, r.updated_at = $now
    ON MATCH SET r.updated_at = $now
    RETURN type(r) AS relation_type
    """

    _QUERY_GET_NEIGHBORS = """
    MATCH (e:Entity {entity_id: $entity_id})-[r:RELATED_TO]-(n:Entity)
    RETURN
        n.entity_id AS entity_id,
        n.name AS name,
        n.entity_type AS entity_type,
        n.aliases AS aliases,
        type(r) AS relation_type,
        coalesce(r.weight, 1.0) AS weight
    ORDER BY weight DESC, n.updated_at DESC
    LIMIT $max_results
    """

    _QUERY_MULTI_HOP_1 = """
    MATCH (seed:Entity)
    WHERE seed.entity_id IN $entity_ids
    MATCH p=(seed)-[*1..1]-(node)
    WHERE node:Entity OR node:Fact
    WITH node, min(length(p)) AS min_hop
    RETURN
        CASE WHEN node:Entity THEN 'Entity' ELSE 'Fact' END AS node_type,
        CASE WHEN node:Entity THEN node.entity_id ELSE node.fact_id END AS node_id,
        properties(node) AS node_properties,
        min_hop AS hop,
        (1.0 / toFloat(min_hop)) AS score
    ORDER BY score DESC, coalesce(node.updated_at, node.created_at) DESC
    LIMIT $limit
    """

    _QUERY_MULTI_HOP_2 = """
    MATCH (seed:Entity)
    WHERE seed.entity_id IN $entity_ids
    MATCH p=(seed)-[*1..2]-(node)
    WHERE node:Entity OR node:Fact
    WITH node, min(length(p)) AS min_hop
    RETURN
        CASE WHEN node:Entity THEN 'Entity' ELSE 'Fact' END AS node_type,
        CASE WHEN node:Entity THEN node.entity_id ELSE node.fact_id END AS node_id,
        properties(node) AS node_properties,
        min_hop AS hop,
        (1.0 / toFloat(min_hop)) AS score
    ORDER BY score DESC, coalesce(node.updated_at, node.created_at) DESC
    LIMIT $limit
    """

    _FACT_ENTITY_RELATION_QUERIES: Dict[str, str] = {
        "MENTIONS": _QUERY_LINK_FACT_MENTIONS_ENTITY,
    }

    _ENTITY_RELATION_QUERIES: Dict[str, str] = {
        "RELATED_TO": _QUERY_LINK_ENTITY_RELATED_TO,
    }

    _QUERY_MULTI_HOP_BY_DEPTH: Dict[int, str] = {
        1: _QUERY_MULTI_HOP_1,
        2: _QUERY_MULTI_HOP_2,
    }

    EXAMPLE_CYPHER = "MATCH (f:Fact)-[:MENTIONS]->(e:Entity) RETURN f.fact_id, e.entity_id LIMIT 5"

    def __init__(
            self,
            uri: str,
            username: str,
            password: str,
            database: str = "neo4j",
    ) -> None:
        """初始化图存储实例并建立可复用驱动。"""
        self.driver: Driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database
        self._close_lock = threading.Lock()
        self._closed = False

    def __enter__(self) -> "Neo4jGraphStore":
        """支持 with 语法。"""
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """退出上下文时释放连接。"""
        self.close()

    def initialize_schema(self) -> None:
        """初始化图 schema（唯一约束与常用索引）。"""
        for query in self._SCHEMA_QUERIES:
            self._execute_write(query)

    def upsert_entity(self, entity: Entity) -> None:
        """按 entity_id 幂等写入实体，并更新 updated_at。"""
        now = datetime.now(timezone.utc)
        aliases = self._deduplicate_aliases(entity.aliases)
        params = {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "aliases": aliases,
            "created_at": self._ensure_aware_datetime(entity.created_at),
            "updated_at": self._ensure_aware_datetime(now),
        }
        self._execute_write(self._QUERY_UPSERT_ENTITY, params)

    def upsert_fact(self, fact: SemanticFact) -> None:
        """按 fact_id 幂等写入事实，并更新 updated_at。"""
        now = datetime.now(timezone.utc)
        params = {
            "fact_id": fact.fact_id,
            "content": fact.content,
            "user_id": fact.user_id,
            "importance": float(fact.importance),
            "confidence": float(fact.confidence),
            "created_at": self._ensure_aware_datetime(fact.created_at),
            "updated_at": self._ensure_aware_datetime(now),
        }
        self._execute_write(self._QUERY_UPSERT_FACT, params)

    def link_fact_entity(
            self,
            fact_id: str,
            entity_id: str,
            relation_type: str = "MENTIONS",
    ) -> None:
        """创建事实到实体关系；若节点不存在则抛出明确异常。"""
        relation_key = relation_type.strip().upper()
        query = self._FACT_ENTITY_RELATION_QUERIES.get(relation_key)
        if query is None:
            raise InvalidRelationTypeError(f"不支持的 Fact->Entity 关系类型: {relation_type}")

        self._assert_fact_exists(fact_id)
        self._assert_entity_exists(entity_id)

        params = {
            "fact_id": fact_id,
            "entity_id": entity_id,
            "now": datetime.now(timezone.utc),
        }
        self._execute_write(query, params)

    def link_entities(
            self,
            source_entity_id: str,
            target_entity_id: str,
            relation_type: str = "RELATED_TO",
            weight: float = 1.0,
    ) -> None:
        """创建实体到实体关系；若节点不存在则抛出明确异常。"""
        relation_key = relation_type.strip().upper()
        query = self._ENTITY_RELATION_QUERIES.get(relation_key)
        if query is None:
            raise InvalidRelationTypeError(f"不支持的 Entity->Entity 关系类型: {relation_type}")

        self._assert_entity_exists(source_entity_id)
        self._assert_entity_exists(target_entity_id)

        params = {
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "weight": float(weight),
            "now": datetime.now(timezone.utc),
        }
        self._execute_write(query, params)

    def get_neighbors(self, entity_id: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """查询实体的一跳邻居，返回邻居实体与关系信息。"""
        if max_results <= 0:
            return []

        self._assert_entity_exists(entity_id)
        params = {"entity_id": entity_id, "max_results": int(max_results)}
        records = self._execute_read(self._QUERY_GET_NEIGHBORS, params)
        return [
            {
                "entity": {
                    "entity_id": item.get("entity_id"),
                    "name": item.get("name"),
                    "entity_type": item.get("entity_type"),
                    "aliases": item.get("aliases") or [],
                },
                "relation_type": item.get("relation_type"),
                "weight": float(item.get("weight", 1.0)),
            }
            for item in records
        ]

    def multi_hop_search(
            self,
            entity_ids: List[str],
            max_hops: int = 2,
            limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """执行 1~2 hop 图扩散检索，并按路径衰减分返回结果。"""
        if limit <= 0:
            return []

        normalized_ids = [item.strip() for item in entity_ids if isinstance(item, str) and item.strip()]
        if not normalized_ids:
            return []

        if max_hops not in self._QUERY_MULTI_HOP_BY_DEPTH:
            raise ValueError("max_hops 仅支持 1 或 2")

        query = self._QUERY_MULTI_HOP_BY_DEPTH[max_hops]
        params = {"entity_ids": normalized_ids, "limit": int(limit)}
        records = self._execute_read(query, params)

        # 按 node_id 去重，保留分数更高的一条。
        dedup: Dict[str, Dict[str, Any]] = {}
        for item in records:
            node_id = str(item.get("node_id", "")).strip()
            if not node_id:
                continue

            hop = int(item.get("hop") or max_hops)
            score = float(item.get("score") or (1.0 / max(hop, 1)))
            payload = {
                "node_type": item.get("node_type"),
                "node_id": node_id,
                "hop": hop,
                "score": score,
                "properties": item.get("node_properties") or {},
            }

            current = dedup.get(node_id)
            if current is None or payload["score"] > float(current.get("score", 0.0)):
                dedup[node_id] = payload

        result = list(dedup.values())
        result.sort(key=lambda x: (float(x["score"]), -int(x["hop"])), reverse=True)
        return result[:limit]

    def mark_superseded(self, old_fact_id: str, new_fact_id: str) -> None:
        """将旧事实标记为被新事实取代。"""
        self._assert_fact_exists(old_fact_id)
        self._assert_fact_exists(new_fact_id)

        params = {
            "old_fact_id": old_fact_id,
            "new_fact_id": new_fact_id,
            "now": datetime.now(timezone.utc),
        }
        self._execute_write(self._QUERY_MARK_SUPERSEDED, params)

    def close(self) -> None:
        """关闭 Neo4j 驱动并释放连接池资源。"""
        with self._close_lock:
            if self._closed:
                return
            self.driver.close()
            self._closed = True

    def _execute_write(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行写事务并返回标准化字典结果。"""
        payload = params or {}
        try:
            with self.driver.session(database=self._database) as session:
                records = session.execute_write(lambda tx: list(tx.run(cypher, payload)))
                return [dict(record) for record in records]
        except Neo4jError as exc:
            raise GraphStoreError(f"Neo4j 写操作失败: {exc}") from exc

    def _execute_read(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行读事务并返回标准化字典结果。"""
        payload = params or {}
        try:
            with self.driver.session(database=self._database) as session:
                records = session.execute_read(lambda tx: list(tx.run(cypher, payload)))
                return [dict(record) for record in records]
        except Neo4jError as exc:
            raise GraphStoreError(f"Neo4j 读操作失败: {exc}") from exc

    def _assert_entity_exists(self, entity_id: str) -> None:
        """校验实体节点存在。"""
        rows = self._execute_read(self._QUERY_CHECK_ENTITY_EXISTS, {"entity_id": entity_id})
        if not rows:
            raise NodeNotFoundError(f"Entity 不存在: {entity_id}")

    def _assert_fact_exists(self, fact_id: str) -> None:
        """校验事实节点存在。"""
        rows = self._execute_read(self._QUERY_CHECK_FACT_EXISTS, {"fact_id": fact_id})
        if not rows:
            raise NodeNotFoundError(f"Fact 不存在: {fact_id}")

    @staticmethod
    def _deduplicate_aliases(aliases: List[str]) -> List[str]:
        """去重并清洗别名，保持输入顺序。"""
        seen: set[str] = set()
        result: List[str] = []
        for alias in aliases:
            text = alias.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _ensure_aware_datetime(value: datetime) -> datetime:
        """确保时间为带时区 datetime。"""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
