"""변경 유형별로 Neo4j에 증분 데이터를 반영하는 Cypher 함수 모음.
신규·수정 객체의 노드·속성·위치·IN 관계를 반영하고,
미관측 객체는 현재 IN 관계를 제거한 뒤 tombstone으로 전환한다.
"""
from benchmark.batch_ops import prepare_active_row

KEYS = ("nodes_created", "nodes_deleted", "relationships_created", "relationships_deleted",
        "labels_added", "labels_removed", "properties_set")


def new_counter_accumulator():
    return {k:0 for k in KEYS}


def accumulate(acc, counters):
    for key in KEYS:
        acc[key] += getattr(counters, key)


def tombstone_batch(tx, nf_ids):
    """미관측 ID의 IN 관계를 제거하고 마지막 관측 정보를 가진 tombstone으로 전환."""
    return tx.run("""
        UNWIND $nf_ids AS nf_id MATCH (p:POI {nf_id:nf_id})
        OPTIONAL MATCH (p)-[r:IN]-(:adm_dong)
        WITH p, collect(r) AS rels
        FOREACH (r IN rels | DELETE r)
        REMOVE p:POI
        SET p:POITombstone, p.last_seen_snapshot='2024',
            p.absent_since_snapshot='2026'
        """, nf_ids=nf_ids).consume().counters


def upsert_batch(tx, rows):
    """신규·수정 POI의 속성·좌표·IN 관계를 한 트랜잭션 안에서 반영."""
    s1 = tx.run("""
        UNWIND $rows AS row MERGE (p:POI {nf_id:row.nf_id})
        SET p += row.properties
        SET p.location = point({longitude:row.longitude, latitude:row.latitude})
        """, rows=rows).consume().counters
    s2 = tx.run("""
        UNWIND $rows AS row MATCH (p:POI {nf_id:row.nf_id})
        OPTIONAL MATCH (p)-[r:IN]-(:adm_dong) DELETE r
        """, rows=rows).consume().counters
    s3 = tx.run("""
        UNWIND $rows AS row MATCH (p:POI {nf_id:row.nf_id})
        MATCH (a:adm_dong) WHERE a.adm_cd=row.adm_cd
        MERGE (p)-[:IN]->(a)
        """, rows=rows).consume().counters
    return [s1,s2,s3]
