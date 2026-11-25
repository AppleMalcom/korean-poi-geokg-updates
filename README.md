# 국가관심지점정보 기반 공간지식그래프의 증분 갱신과 전체 재구축 성능 비교

대한공간정보학회 2026 추계학술대회에서 발표한 연구의 **구현 참고용 코드**입니다. 서울대학교 건설환경도시공학부 공간정보센터 석사과정 이창현의 발표 내용을 기준으로 정리했습니다.

두 시점의 국가관심지점정보(국가 POI)를 비교하여 Neo4j 공간지식그래프를 갱신하고, 전체 재구축(Batch Rebuild)과 증분 갱신(Incremental Update)의 처리 시간 및 논리적 쓰기 연산량을 비교했습니다. 준비된 연구 DB를 사용한 구현이며, 원천 데이터와 DB 설치·초기 구축 과정은 공개 범위에 포함하지 않습니다.

## 1. Batch와 증분 갱신 코드

아래 순서로 읽으면 두 갱신 방식과 실험의 연결을 확인할 수 있습니다.

| 코드 | 발표에서의 역할 |
| --- | --- |
| [batch_ops.py](benchmark/batch_ops.py) | 기존 POI 제거와 T2 전체 적재: POI 노드·좌표·행정동 IN 관계 생성 |
| [change_detection.py](benchmark/change_detection.py) | PostgreSQL/PostGIS에서 nf_id 기준으로 두 스냅샷을 비교하고 변경 객체 추출 |
| [incremental_ops.py](benchmark/incremental_ops.py) | Appear·Updated 반영과 Disappear의 tombstone 전환 |
| [execution.py](benchmark/execution.py) | 데이터 전달, 트랜잭션 분할, T1 복원, 단계별 시간 측정 |
| [validation.py](benchmark/validation.py) | 활성 ID·감시 속성·좌표 갱신 정책·IN 관계·tombstone 검증 |

그래프의 계층은 `POI —IN→ 행정동 —BELONG_TO→ 시군구 —BELONG_TO→ 시도`입니다. 실험에서는 POI와 IN 관계를 갱신하고, 미리 구성한 행정구역 계층은 유지했습니다. Neo4j의 LPG 모델을 사용하며, RDF 트리플 갱신 코드는 아닙니다.

### 변경 탐지 및 반영 기준

- 입력: T1 **2024년 11월**, T2 **2026년 1월** 국가 POI 스냅샷.
- 식별자: `nf_id`.
- 감시 속성: 명칭 `poi_nm`, 분류코드 `poi_cl_dc`, 소속 행정동 `adm_cd`, 위치 `geom`.
- 위치 변경: EPSG:5179에서 **1m 초과**. 1m는 미세한 위치 차이를 제외하기 위한 운영적 허용오차이며 보편적 최적값을 의미하지 않습니다.
- 행정동은 공간 포함관계로 사전 계산하며, Neo4j에는 EPSG:4326 기반 `point`로 좌표를 저장합니다.

| 유형 | 판정 | 그래프 반영 |
| --- | --- | --- |
| Appear | T1에 없고 T2에 있는 ID | POI 생성 및 IN 관계 연결 |
| Updated | 공통 ID의 감시 속성 변경 또는 위치 1m 초과 이동 | 속성·위치 갱신 및 IN 관계 재연결 |
| Disappear | T1에 있고 T2에 없는 ID | IN 제거, POI 라벨 제거, POITombstone 전환 |
| No Change | 위 변경 기준에 해당하지 않음 | T1 상태 유지 |

증분 갱신에서는 변경되지 않은 객체의 T1 속성과 좌표를 유지합니다. 따라서 두 방식의 모든 속성·좌표가 T2와 완전히 동일하다는 의미는 아닙니다.

## 2. 실험 1·2 실행 코드

| 진입점 | 범위 | 트랜잭션 크기 | 본측정 |
| --- | --- | --- | --- |
| [experiment_1.py](experiment_1.py) | 서울특별시 전체 | 최대 1,000 POI | 방식별 3회 |
| [experiment_2.py](experiment_2.py) | 서울시 25개 자치구 | 최대 5,000 POI | 구별·방식별 3회 |
| [benchmark_runner.py](benchmark_runner.py) | 공통 실행기 | 인자로 지정 | 복원·반복·측정·검증·CSV 기록 |

워밍업은 본측정과 분리하여 수행했습니다. 두 진입점은 본측정만 실행하며, `--apply` 없이는 PostgreSQL에서 건수만 조회합니다. 세부 흐름과 참고 명령은 [코드 안내](benchmark/README.md), 측정 범위와 검증 정의는 [실험 설계](docs/experiment_design.md)에 정리했습니다.

### 발표 결과 요약

| 항목 | Batch | Incremental | 시간 절감률 |
| --- | --- | --- | --- |
| 실험 1: 서울 전체 | 488.163초 | 450.163초 | 7.78% |
| 실험 2: 자치구 평균 | 21.359초 | 18.221초 | 자치구별 절감률 평균 15.33% |

실험 1에서는 노드 생성 50.16%, 관계 생성 48.50%, 속성 설정 40.25% 감소를 확인했습니다. 실험 2에서는 25개 구 모두 증분 갱신이 빨랐으며, 변경률이 높을수록 상대적 시간 절감 효과가 감소하는 경향을 관찰했습니다. 실험 1의 본측정 6회와 실험 2의 본측정 150회는 정의된 정합성 검증을 통과했습니다.

실험 2의 15.33%는 **구별 절감률을 먼저 구한 뒤 평균한 값**입니다. 표의 두 평균 시간으로 직접 계산한 절감률과는 다릅니다. 두 실험의 트랜잭션 크기가 다르므로, 실험 간 차이를 지역 규모만의 효과로 해석하지 않습니다. 결과는 발표 당시 환경에서 측정한 값이며 이번 공개 정리 과정에서 재측정하지 않았습니다.

## 3. 해석 범위와 연구의 한계

**Appear·Disappear는 nf_id 기준 신규 관측·미관측이며, 실제 시설의 개업·폐업을 뜻하지 않습니다.** 동일 시설이 서로 다른 ID로 제공될 경우 Appear와 Disappear로 나뉠 수 있으나, 본 구현에서는 시점 간 Entity Resolution을 수행하지 않았습니다.

서울 전체의 식별자 기준 변경률은 71.62%이고, Appear와 Disappear가 합집합의 70.65%를 차지했습니다. 높은 변경률을 실제 시설 변화율로 해석할 수 없습니다. 약 14개월 간격의 두 스냅샷과 POI·행정구역 중심의 그래프를 대상으로 평가했으므로, 짧은 갱신 주기 및 다양한 공간정보에 대한 일반화에는 추가 검증이 필요합니다.

## 4. 구현 범위

- SQL 스냅샷 비교 기반 CDC이며, DB 로그를 구독하는 실시간 CDC는 아닙니다.
- IncRML의 watched properties 기반 증분 개념을 참고하여 구현했습니다. IncRML 엔진이나 RML 매핑을 직접 실행하지 않습니다.
- 연결 설정의 형식은 [.env.example](.env.example), Python 의존성은 [requirements.txt](requirements.txt)에 있습니다.
- 데이터·결과 CSV·DB 덤프·개인 연결 설정·보조 분석 및 전처리 스크립트는 공개 대상에서 제외했습니다.
- 쓰기 실행은 매 회차 Neo4j의 모든 POI·POITombstone을 제거한 뒤 대상 범위의 T1을 복원합니다. 지역별 실행도 기존 그래프 일부만 되돌리는 구조가 아니므로 전용 실험 DB를 전제로 합니다.

## 참고한 선행연구

발표에서 소개한 주요 선행연구입니다.

- Van Assche et al. (2026), *Incremental knowledge graph construction from heterogeneous data sources*: 감시 속성 기반 증분 구축 개념.
- 김동현·장한메·유기윤 (2022), *효율적인 공간분석질의 수행을 위한 한국형 공간지식그래프 구축방안에 관한 연구: 서울시를 대상으로*: IN·BELONG_TO 관계를 이용한 GeoKG 구성.
- Hofer et al. (2024), *Construction of knowledge graphs: Current state and challenges*: KG 구축·갱신의 확장성 문제.
