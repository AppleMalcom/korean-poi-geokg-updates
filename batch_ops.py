"""전체 재구축(Batch) 방식의 Neo4j 처리 함수를 모은 코드.
POI·tombstone 삭제, 전체 POI 노드·위치·IN 관계 적재와 쓰기량 집계를 담당한다.
원천 레코드를 Neo4j 속성으로 변환하는 공통 함수도 제공한다.
"""
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from uuid import UUID

EXCLUDED_PROPERTIES = {"geom", "change_type", "snapshot"}



def convert_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(
        value,
        (str, int, float, bool, bytes, date, datetime, datetime_time),
    ):
        return value
    return str(value)


def prepare_active_row(row):
    properties = {
        key: convert_value(value)
        for key, value in row.items()
        if key not in EXCLUDED_PROPERTIES
    }
    return {
        "nf_id": str(row["nf_id"]),
        "adm_cd": str(row["adm_cd"]),
        "longitude": float(row["longitude"]),
        "latitude": float(row["latitude"]),
        "properties": properties,
    }


def delete_label_batch(tx, label, batch_size):
    """라벨 노드를 LIMIT 단위로 DETACH DELETE. 반환: 삭제된 노드 수."""
    result = tx.run(
        f"""
        MATCH (p:{label})
        WITH p LIMIT $batch_size
        DETACH DELETE p
        """,
        batch_size=batch_size,
    )
    return result.consume().counters


def rebuild_upsert_batch(tx, rows):
    """입력 스냅샷의 POI·위치·IN 관계 적재: T1 복원과 T2 Batch에 공통 사용."""
    s1 = tx.run(
        """
        UNWIND $rows AS row
        MERGE (p:POI {nf_id: row.nf_id})
        SET p += row.properties
        SET p.location = point({
            longitude: row.longitude,
            latitude: row.latitude
        })
        """,
        rows=rows,
    ).consume()

    s2 = tx.run(
        """
        UNWIND $rows AS row
        MATCH (p:POI {nf_id: row.nf_id})
        MATCH (a:adm_dong)
        WHERE a.adm_cd = row.adm_cd
        MERGE (p)-[r:IN]->(a)
        """,
        rows=rows,
    ).consume()

    return [s1.counters, s2.counters]


def new_counter_accumulator():
    return {
        "nodes_created": 0,
        "nodes_deleted": 0,
        "relationships_created": 0,
        "relationships_deleted": 0,
        "labels_added": 0,
        "labels_removed": 0,
        "properties_set": 0,
    }


def accumulate(acc, counters):
    acc["nodes_created"] += counters.nodes_created
    acc["nodes_deleted"] += counters.nodes_deleted
    acc["relationships_created"] += counters.relationships_created
    acc["relationships_deleted"] += counters.relationships_deleted
    acc["labels_added"] += counters.labels_added
    acc["labels_removed"] += counters.labels_removed
    acc["properties_set"] += counters.properties_set


def delete_all_poi_nodes(session, batch_size):
    """현재 :POI / :POITombstone 노드를 모두 삭제한다.

    반환: 누적 counters (측정 구간에서 재사용).
    """
    acc = new_counter_accumulator()
    for label in ("POI", "POITombstone"):
        while True:
            counters = session.execute_write(
                delete_label_batch, label, batch_size
            )
            accumulate(acc, counters)
            if counters.nodes_deleted == 0:
                break
    return acc
