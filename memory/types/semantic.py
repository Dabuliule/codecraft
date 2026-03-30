"""SemanticMemory 实现：知识图谱 + 向量混合检索。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from memory.base import MemoryBase, MemoryRecord
from memory.storage import (
    EmbeddingService,
    Entity,
    Neo4jGraphStore,
    SemanticFact,
)
from memory.storage.qdrant_semantic_vector_store import QdrantSemanticVectorStore


@dataclass(frozen=True)
class SemanticMemoryRecord(MemoryRecord):
    """语义记忆记录：结构化知识表示。"""

    content: str = ""
    entity_ids: List[str] = field(default_factory=list)
    user_id: str = ""
    confidence: float = 0.0
    vector_score: float = 0.0
    graph_score: float = 0.0


class SemanticMemory(MemoryBase):
    """语义记忆：基于图 + 向量的混合知识存储与检索。"""

    # Entity 抽取的正则规则
    _ENGLISH_WORD_PATTERN = re.compile(r"[A-Za-z]{2,}")
    _CHINESE_WORD_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,4}")

    _RELATION_SCHEMA: set[str] = {
        "USES",
        "DEPENDS_ON",
        "STORES_IN",
        "RETRIEVES_FROM",
        "CAUSES",
        "SOLVES",
        "IMPLEMENTS",
        "RELATED_TO",
    }

    _RELATION_KEYWORDS: Dict[str, tuple[str, ...]] = {
        "USES": ("使用", "调用", "用", "uses", "use", "using", "calls"),
        "DEPENDS_ON": ("依赖", "基于", "depends on", "depend on", "based on"),
        "STORES_IN": ("存储", "保存到", "stores in", "store in"),
        "RETRIEVES_FROM": ("检索", "读取", "retrieves from", "retrieve from", "reads from"),
        "CAUSES": ("导致", "引发", "causes", "lead to", "leads to"),
        "SOLVES": ("解决", "修复", "solves", "fixes", "resolve"),
        "IMPLEMENTS": ("实现", "implements", "implement"),
    }

    _RELATION_VERB_MAPPING: Dict[str, str] = {
        "使用": "USES",
        "调用": "USES",
        "依赖": "DEPENDS_ON",
        "基于": "DEPENDS_ON",
        "存储": "STORES_IN",
        "保存": "STORES_IN",
        "检索": "RETRIEVES_FROM",
        "读取": "RETRIEVES_FROM",
        "导致": "CAUSES",
        "引发": "CAUSES",
        "解决": "SOLVES",
        "修复": "SOLVES",
        "实现": "IMPLEMENTS",
        "use": "USES",
        "uses": "USES",
        "using": "USES",
        "call": "USES",
        "calls": "USES",
        "depend": "DEPENDS_ON",
        "depends": "DEPENDS_ON",
        "store": "STORES_IN",
        "stores": "STORES_IN",
        "retrieve": "RETRIEVES_FROM",
        "retrieves": "RETRIEVES_FROM",
        "read": "RETRIEVES_FROM",
        "reads": "RETRIEVES_FROM",
        "cause": "CAUSES",
        "causes": "CAUSES",
        "solve": "SOLVES",
        "solves": "SOLVES",
        "implement": "IMPLEMENTS",
        "implements": "IMPLEMENTS",
    }

    _SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？!?;；\n]+")

    def __init__(
        self,
        graph_store: Neo4jGraphStore,
        vector_store: QdrantSemanticVectorStore,
        embedding_service: EmbeddingService,
        default_user_id: str = "default",
    ) -> None:
        """初始化语义记忆。"""
        if not default_user_id.strip():
            raise ValueError("default_user_id 不能为空")

        self._graph = graph_store
        self._vector = vector_store
        self._embedding = embedding_service
        self._default_user_id = default_user_id

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        """按 fact_id 获取完整记录。"""
        return None

    def list(self, limit: Optional[int] = None) -> List[MemoryRecord]:
        """按创建时间列出最近的 N 条知识。"""
        if limit is not None and limit <= 0:
            return []
        return []

    def retrieve(self, query: Optional[str] = None, limit: int = 5) -> List[MemoryRecord]:
        """执行混合检索：向量 + 图扩散 + score fusion。"""
        if limit <= 0:
            return []

        if not query or not query.strip():
            return []

        # Step 1: 向量召回
        query_embedding = self._embedding.embed(query)
        vector_results = self._vector.search(
            embedding=query_embedding,
            limit=max(limit * 3, 20),
            user_id=self._default_user_id,
        )

        if not vector_results:
            return []

        # Step 2: 聚合 entity_ids
        all_entity_ids: set[str] = set()
        for result in vector_results:
            all_entity_ids.update(result.get("entity_ids", []))

        # Step 3: 图扩散检索
        graph_results: Dict[str, Dict[str, Any]] = {}
        if all_entity_ids:
            graph_hits = self._graph.multi_hop_search(
                entity_ids=list(all_entity_ids),
                max_hops=2,
                limit=50,
            )
            for hit in graph_hits:
                node_id = hit.get("node_id", "")
                hop = int(hit.get("hop", 2))
                score = float(hit.get("score", 0.0))
                if node_id:
                    graph_results[node_id] = {
                        "hop": hop,
                        "graph_score": score,
                    }

        # Step 4: Score fusion
        scored_records: List[tuple[float, SemanticMemoryRecord]] = []
        for vec_result in vector_results:
            fact_id = vec_result["fact_id"]
            vector_score = vec_result["vector_score"]
            graph_score = graph_results.get(fact_id, {}).get("graph_score", 0.0)
            importance = vec_result["importance"]

            # 融合评分公式
            final_score = (
                vector_score * 0.7
                + graph_score * 0.2
                + importance * 0.1
            )

            record = SemanticMemoryRecord(
                record_id=fact_id,
                content="",  # 暂时不存储完整内容
                entity_ids=vec_result.get("entity_ids", []),
                user_id=vec_result.get("user_id", ""),
                importance=importance,
                confidence=vec_result["confidence"],
                vector_score=vector_score,
                graph_score=graph_score,
                created_at=datetime.now(ZoneInfo("Asia/Shanghai")),
            )
            scored_records.append((final_score, record))

        # Step 5: 按分数排序并返回
        scored_records.sort(key=lambda x: x[0], reverse=True)
        return [record for _, record in scored_records[:limit]]

    def delete(self, record_id: str) -> bool:
        """删除知识记录（暂时 stub）。"""
        return False

    def clear(self) -> None:
        """清空所有知识（暂时 stub）。"""
        pass

    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """添加知识：写入 fact、抽取实体和关系、写入图与向量。"""
        if not content or not content.strip():
            raise ValueError("content 不能为空")

        content = content.strip()
        metadata = metadata or {}
        user_id = metadata.get("user_id", self._default_user_id)
        importance = float(metadata.get("importance", 0.5))
        confidence = float(metadata.get("confidence", 0.8))

        # Step 1: 生成 fact_id 与 embedding
        fact_id = f"fact_{uuid.uuid4().hex}"
        embedding = self._embedding.embed(content)

        # Step 2: 构建并写入事实
        fact = SemanticFact(
            fact_id=fact_id,
            content=content,
            user_id=user_id,
            importance=importance,
            confidence=confidence,
        )
        self._graph.upsert_fact(fact)

        # Step 3: 抽取实体
        entities = self._extract_entities(content, metadata)
        entity_ids = [entity.entity_id for entity in entities]

        # Step 4: 写入实体与 Fact-Entity 关系
        for entity in entities:
            self._graph.upsert_entity(entity)
            self._graph.link_fact_entity(
                fact_id=fact_id,
                entity_id=entity.entity_id,
                relation_type="MENTIONS",
            )

        # Step 5: 抽取并写入 Entity-Entity 关系
        relations = self._extract_relations(content=content, entities=entities)
        for source_entity_id, relation_type, target_entity_id in relations:
            self._graph.link_entities(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
                weight=1.0,
            )

        # Step 6: 写入向量存储
        self._vector.upsert(
            fact_id=fact_id,
            embedding=embedding,
            entity_ids=entity_ids,
            user_id=user_id,
            importance=importance,
            confidence=confidence,
        )

        return fact_id

    def consolidate(self, similarity_threshold: float = 0.9) -> int:
        """合并相似的知识（MVP 暂不实现，返回 0）。"""
        return 0

    def _extract_entities(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Entity]:
        """轻量级实体抽取：优先 metadata，然后启发式抽取。"""
        names: set[str] = set()

        # 优先从 metadata 获取显式实体
        if metadata and "entities" in metadata:
            explicit = metadata["entities"]
            if isinstance(explicit, list):
                names.update(str(e).strip() for e in explicit if str(e).strip())

        # 英文连续词
        for match in self._ENGLISH_WORD_PATTERN.finditer(content):
            word = match.group(0)
            if len(word) >= 3 and word.lower() != "the":
                names.add(word)

        # 中文 2~4 字词组
        for match in self._CHINESE_WORD_PATTERN.finditer(content):
            names.add(match.group(0))

        entities: List[Entity] = []
        for name in list(names)[:20]:
            entity_id = self._to_entity_id(name)
            entities.append(
                Entity(
                    entity_id=entity_id,
                    name=name,
                    entity_type="Concept",
                    aliases=[name],
                )
            )
        return entities

    def _extract_relations(self, content: str, entities: List[Entity]) -> List[Tuple[str, str, str]]:
        """抽取实体关系：规则优先，依存分析增强，输出归一化 schema。"""
        if len(entities) < 2:
            return []

        relation_set: set[Tuple[str, str, str]] = set()
        for item in self._extract_relations_rule_based(content=content, entities=entities):
            relation_set.add(item)
        for item in self._extract_relations_dependency_based(content=content, entities=entities):
            relation_set.add(item)
        return sorted(relation_set)

    def _extract_relations_rule_based(
        self,
        content: str,
        entities: List[Entity],
    ) -> List[Tuple[str, str, str]]:
        """基于关键词规则抽取关系，是当前 MVP 主路径。"""
        results: set[Tuple[str, str, str]] = set()
        sentences = [part.strip() for part in self._SENTENCE_SPLIT_PATTERN.split(content) if part.strip()]

        for sentence in sentences:
            lowered_sentence = sentence.lower()
            hits = self._find_sentence_entity_hits(sentence=sentence, entities=entities)
            if len(hits) < 2:
                continue

            for relation_type, keywords in self._RELATION_KEYWORDS.items():
                for keyword in keywords:
                    positions = self._find_keyword_positions(sentence=sentence, lowered_sentence=lowered_sentence, keyword=keyword)
                    if not positions:
                        continue

                    for start, end in positions:
                        left = [item for item in hits if item[1] < start]
                        right = [item for item in hits if item[1] >= end]

                        if left and right:
                            source_id = left[-1][0]
                            for target_id, _ in right:
                                if source_id != target_id:
                                    results.add((source_id, relation_type, target_id))
                        elif len(hits) >= 2:
                            source_id = hits[0][0]
                            for target_id, _ in hits[1:]:
                                if source_id != target_id:
                                    results.add((source_id, relation_type, target_id))
        return sorted(results)

    def _extract_relations_dependency_based(
        self,
        content: str,
        entities: List[Entity],
    ) -> List[Tuple[str, str, str]]:
        """依存句法增强抽取：英文优先 spaCy，中文优先 HanLP。"""
        results: set[Tuple[str, str, str]] = set()
        for item in self._extract_relations_spacy(content=content, entities=entities):
            results.add(item)
        for item in self._extract_relations_hanlp(content=content, entities=entities):
            results.add(item)
        return sorted(results)

    def _extract_relations_spacy(
        self,
        content: str,
        entities: List[Entity],
    ) -> List[Tuple[str, str, str]]:
        """使用 spaCy 进行英文依存句法关系抽取。"""
        try:
            import spacy
        except ImportError:
            return []

        model = getattr(self, "_spacy_nlp", None)
        if model is None:
            try:
                model = spacy.load("en_core_web_sm")
                setattr(self, "_spacy_nlp", model)
            except OSError:
                return []

        results: set[Tuple[str, str, str]] = set()
        doc = model(content)
        for token in doc:
            if token.pos_ != "VERB":
                continue
            relation = self._normalize_relation_type(token.lemma_)
            if relation is None:
                continue

            subj_text = ""
            obj_text = ""
            for child in token.children:
                if child.dep_ in {"nsubj", "nsubjpass"}:
                    subj_text = child.text
                elif child.dep_ in {"dobj", "pobj", "attr", "obl"}:
                    obj_text = child.text

            source_id = self._match_entity_id(subj_text, entities)
            target_id = self._match_entity_id(obj_text, entities)
            if source_id and target_id and source_id != target_id:
                results.add((source_id, relation, target_id))
        return sorted(results)

    def _extract_relations_hanlp(
        self,
        content: str,
        entities: List[Entity],
    ) -> List[Tuple[str, str, str]]:
        """使用 HanLP 进行中文依存句法关系抽取（可选增强）。"""
        try:
            import hanlp
        except ImportError:
            return []

        pipeline = getattr(self, "_hanlp_pipeline", None)
        if pipeline is None:
            try:
                pipeline = hanlp.load(hanlp.pretrained.dep.CTB9_DEP_ELECTRA_SMALL)
                setattr(self, "_hanlp_pipeline", pipeline)
            except (AttributeError, OSError):
                return []

        # HanLP 模型输出格式差异较大，MVP 阶段仅在可稳定解析时返回结果。
        try:
            parsed = pipeline(content)
        except (TypeError, ValueError):
            return []

        words = getattr(parsed, "get", lambda _key, _default=None: _default)("tok/fine", [])
        if not isinstance(words, list) or not words:
            return []

        joined = " ".join(str(item) for item in words)
        return self._extract_relations_rule_based(content=joined, entities=entities)

    def _find_sentence_entity_hits(
        self,
        sentence: str,
        entities: List[Entity],
    ) -> List[Tuple[str, int]]:
        """找到句子中命中的实体与其起始位置。"""
        lowered = sentence.lower()
        hits: Dict[str, int] = {}
        for entity in entities:
            variants = [entity.name] + list(entity.aliases or [])
            best_pos: Optional[int] = None
            for variant in variants:
                text = variant.strip()
                if not text:
                    continue
                probe = text.lower()
                pos = lowered.find(probe)
                if pos < 0:
                    pos = sentence.find(text)
                if pos >= 0 and (best_pos is None or pos < best_pos):
                    best_pos = pos
            if best_pos is not None:
                hits[entity.entity_id] = best_pos
        return sorted(hits.items(), key=lambda item: item[1])

    @staticmethod
    def _find_keyword_positions(sentence: str, lowered_sentence: str, keyword: str) -> List[Tuple[int, int]]:
        """查找关键词在句子中的所有位置。"""
        target = keyword.lower() if any("a" <= ch <= "z" for ch in keyword.lower()) else keyword
        haystack = lowered_sentence if target == keyword.lower() else sentence
        positions: List[Tuple[int, int]] = []
        start = 0
        while True:
            idx = haystack.find(target, start)
            if idx < 0:
                break
            positions.append((idx, idx + len(target)))
            start = idx + len(target)
        return positions

    def _normalize_relation_type(self, text: str) -> Optional[str]:
        """将原始动词或关键词归一化为标准关系 schema。"""
        key = text.strip().lower()
        if not key:
            return None
        relation = self._RELATION_VERB_MAPPING.get(key)
        if relation in self._RELATION_SCHEMA:
            return relation
        return None

    @staticmethod
    def _match_entity_id(text: str, entities: List[Entity]) -> Optional[str]:
        """将文本片段匹配到已识别实体。"""
        needle = text.strip().lower()
        if not needle:
            return None
        for entity in entities:
            candidates = [entity.name] + list(entity.aliases or [])
            for candidate in candidates:
                if candidate.strip().lower() == needle:
                    return entity.entity_id
        return None

    @staticmethod
    def _to_entity_id(name: str) -> str:
        """将实体名称转换为稳定可写入图谱的 entity_id。"""
        normalized = re.sub(r"\s+", "_", name.strip().lower())
        normalized = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return f"ent_{normalized or uuid.uuid4().hex[:8]}"

    @staticmethod
    def _fact_to_record(fact: SemanticFact) -> SemanticMemoryRecord:
        """将 SemanticFact 转换为 MemoryRecord。"""
        return SemanticMemoryRecord(
            record_id=fact.fact_id,
            content=fact.content,
            importance=fact.importance,
            user_id=fact.user_id,
            confidence=fact.confidence,
            created_at=fact.created_at,
        )

