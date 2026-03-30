"""Qdrant 向量存储：用于 SemanticMemory 的语义检索。"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models


class QdrantSemanticVectorStore:
    """语义记忆向量存储：负责 fact embedding 与多字段 payload。"""

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        collection_name: str = "semantic_memory",
        vector_size: int = 128,
    ) -> None:
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._client = QdrantClient(url=url, api_key=api_key)
        self._ensure_collection()

    def upsert(
        self,
        fact_id: str,
        embedding: List[float],
        entity_ids: List[str],
        user_id: str,
        importance: float,
        confidence: float,
    ) -> None:
        """写入 fact 与关联的 entity_ids、metadata。"""
        if len(embedding) != self._vector_size:
            raise ValueError(
                f"embedding 维度不匹配: 期望 {self._vector_size}, 实际 {len(embedding)}"
            )

        point_id = self._to_point_id(fact_id)
        payload = {
            "fact_id": fact_id,
            "entity_ids": entity_ids or [],
            "user_id": user_id,
            "importance": float(importance),
            "confidence": float(confidence),
        }
        point = qdrant_models.PointStruct(
            id=point_id,
            vector=embedding,
            payload=payload,
        )
        self._client.upsert(
            collection_name=self._collection_name,
            points=[point],
            wait=True,
        )

    def search(
        self,
        embedding: List[float],
        limit: int = 20,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量检索，支持可选的 user_id 过滤。"""
        if limit <= 0:
            return []
        if len(embedding) != self._vector_size:
            raise ValueError(
                f"embedding 维度不匹配: 期望 {self._vector_size}, 实际 {len(embedding)}"
            )

        # 如果指定 user_id，构建过滤条件
        query_filter = None
        if user_id:
            query_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="user_id",
                        match=qdrant_models.MatchValue(value=user_id),
                    )
                ]
            )

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=embedding,  # type: ignore[arg-type]
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
            with_vectors=False,
        )
        points = getattr(response, "points", response)

        results: List[Dict[str, Any]] = []
        for point in points:
            payload = getattr(point, "payload", {}) or {}
            fact_id = payload.get("fact_id")
            if not fact_id:
                continue
            score = float(getattr(point, "score", 0.0) or 0.0)
            results.append(
                {
                    "fact_id": str(fact_id),
                    "entity_ids": payload.get("entity_ids", []),
                    "user_id": payload.get("user_id", ""),
                    "importance": float(payload.get("importance", 0.5)),
                    "confidence": float(payload.get("confidence", 0.0)),
                    "vector_score": score,
                }
            )
        return results

    def _ensure_collection(self) -> None:
        """确保 collection 存在，如果不存在则创建。"""
        if self._client.collection_exists(self._collection_name):
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=self._vector_size,
                distance=qdrant_models.Distance.COSINE,
            ),
        )

    @staticmethod
    def _to_point_id(fact_id: str) -> int:
        """使用稳定哈希生成 63 位正整数作为 Qdrant point id。"""
        digest = hashlib.sha256(fact_id.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return value & ((1 << 63) - 1)

