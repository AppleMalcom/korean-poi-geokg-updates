# Batch·증분 갱신 및 실험 코드 안내

이 문서는 학술대회에서 사용한 처리 흐름과 실험 실행 방식을 설명합니다. DB 설치나 초기 그래프 구축을 안내하는 문서는 아닙니다.

## 1. Batch Rebuild

`batch_ops.py`는 기존 POI 제거와 전체 적재 Cypher를 제공합니다. `execution.rebuild()`는 다음 흐름을 측정합니다.

1. 기존 POI·POITombstone을 트랜잭션 단위로 제거.
2. PostgreSQL에서 대상 범위의 T2 POI를 nf_id 순서로 조회.
3. Python에서 속성을 변환하여 POI 노드와 WGS-84 point 적재.
4. adm_cd가 일치하는 행정동에 IN 관계 연결.

`rebuild_upsert_batch()`는 T1 복원에도 재사용합니다. 행정구역 노드와 BELONG_TO 계층은 삭제하거나 재구축하지 않습니다.

## 2. Incremental Update

### 변경 탐지: change_detection.py

T1·T2를 nf_id로 FULL JOIN하여 Appear·Updated·Disappear·No Change를 판정합니다. 명칭·분류코드·행정동은 `IS DISTINCT FROM`, 위치는 `NOT ST_DWithin(t1.geom, t2.geom, 1.0)`으로 비교합니다. 발표 입력은 EPSG:5179이며 geometry 결측이 없는 데이터입니다.

신규·수정은 T2 전체 행, 미관측은 T1 전체 행을 증분 테이블 `mart.benchmark_inc_poi`에 저장합니다. No Change는 저장하지 않습니다. 같은 증분 테이블을 공유하므로 여러 실험 프로세스를 동시에 실행하는 용도는 아닙니다.

### 증분 반영: incremental_ops.py

`execution.apply_delta()`는 Disappear → Appear → Updated 순서로 반영합니다.

- Disappear: 현재 IN 관계 제거 → POI 라벨 제거 → POITombstone 라벨 및 관측 시점 속성 설정. 노드의 기존 속성과 마지막 위치는 보존.
- Appear·Updated: POI MERGE → T2 속성·좌표 반영 → 기존 IN 제거 → 현재 행정동으로 IN 연결.
- No Change: 기존 T1 상태 유지.

신규·수정 반영에서 세 Cypher 문은 동일 트랜잭션 안에서 수행합니다. 미관측은 물리적 삭제가 아니며, tombstone의 관측 시점은 이 연구의 T1='2024', T2='2026'에 고정돼 있습니다. 다중 시점 운영을 위한 범용 이력 관리기는 아닙니다.

## 3. 실험 1: 서울 전체

`experiment_1.py`는 공통 실행기에 아래 조건을 전달하는 얇은 진입점입니다.

- `--all-seoul --experiment1-three --batch-size 1000`
- 서울 전체를 하나의 범위로 처리.
- 사전 워밍업은 별도 파일로 분리. 본측정은 Incremental → Batch를 3쌍 실행.
- 각 실행 전에 대상 범위의 T1을 재구성하고 기준 ID를 확인.

발표 실행 방식의 참고 명령입니다. 기본 실행도 준비된 PostgreSQL 연결이 필요합니다.

```powershell
# 건수만 확인: Neo4j 갱신 없음
python experiment_1.py

# 별도 워밍업: 각 방식 1회. 파일 안 role은 measure이므로 본측정과 파일로 분리
python benchmark_runner.py --all-seoul --pilot --batch-size 1000 --output results/experiment_1/new_warmup.csv --apply --confirm-destructive-benchmark

# 본측정: 각 방식 3회, 워밍업 제외
python experiment_1.py --output results/experiment_1/new_measurements.csv --apply --confirm-destructive-benchmark
```

## 4. 실험 2: 서울 25개 자치구

`experiment_2.py`는 `--experiment2 --skip-warmup --batch-size 5000`을 전달합니다.

- 별도 사전 실행으로 구별·방식별 워밍업 1회 수행.
- 본측정은 25개 구 × 2개 방식 × 3회 = 150회.
- 한 구의 본측정 6회를 마친 뒤 다음 구로 이동.
- 구별 첫 방식을 교대: A구 Inc → Batch × 3쌍, B구 Batch → Inc × 3쌍.
- 구별 방식 평균·표본 표준편차·시간 절감률을 요약 CSV로 기록.
- 구 경계를 넘는 공통 ID는 구별로 Appear·Disappear로, 서울 전체에서는 Updated로 분류될 수 있음.

```powershell
# 건수만 확인
python experiment_2.py

# 별도 워밍업: 25개 구 각각 Batch 1회 + Incremental 1회
python benchmark_runner.py --pilot --batch-size 5000 --output results/experiment_2/new_warmup_5000.csv --apply --confirm-destructive-benchmark

# 본측정 150회만 실행
python experiment_2.py --output results/experiment_2/new_measurements_5000.csv --apply --confirm-destructive-benchmark
```

공통 실행기는 `--experiment2` 단독일 경우 내장 워밍업을 포함합니다. 발표 조건용 `experiment_2.py`는 별도 워밍업 후의 본측정이므로 이를 건너뜁니다. CSV position은 공통 실행기의 3~8번을 사용합니다.

`--resume`은 검증을 통과한 (지역, position)을 건너뜁니다. CSV에 트랜잭션 크기·DB 환경 등이 저장되지 않으므로, 동일한 입력·설정·범위·순서를 사용하는 경우에만 참고할 수 있습니다. 파일 이름만으로 설정 일치를 검증하지는 않습니다.

## 5. 실행·측정·검증의 관계

```text
공통 전처리와 행정구역 계층 구성 (실험 전에 완료)
    ↓
대상 범위의 T1 복원·기준 검증 (측정 제외)
    ↓
Batch: POI 제거 → T2 전체 적재
또는
Incremental: CDC·증분 테이블 생성 → 변경 유형별 반영
    ↓
정합성 검증·CSV 저장 (측정 제외)
```

`--apply --confirm-destructive-benchmark`를 지정하면 **모든 POI·POITombstone을 삭제한 뒤 T1을 복원**합니다. 자치구 실험도 다른 구의 POI를 보존하는 방식이 아닙니다. PostgreSQL의 mart.poi는 읽지만, 증분 테이블은 생성·비우기·삽입합니다.

측정 경계와 정합성의 정확한 정의는 [실험 설계](../docs/experiment_design.md)를 참조하세요. CSV의 논리적 쓰기량은 Neo4j counters이며 디스크 I/O 바이트가 아닙니다. 입력 데이터와 원시 결과 파일은 공개 범위에 포함하지 않습니다.
