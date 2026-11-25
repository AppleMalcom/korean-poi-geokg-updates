# 국가관심지점정보 기반 공간지식그래프의 증분 갱신과 전체 재구축 성능 비교

- 이 저장소는 대한공간정보학회 2026 추계학술대회에서 발표한 「국가관심지점정보 기반 공간지식그래프의 증분 갱신과 전체 재구축 성능 비교」 논문의 공개 코드입니다.
- 본 연구는 국토교통부/국토교통과학기술진흥원의 지원으로 수행되었습니다(과제번호 RS-2022-00143336).
- 작성자: 서울대학교 건설환경도시공학부 공간정보센터 이창현 전임연구원 ([malcom@snu.ac.kr](mailto:malcom@snu.ac.kr))

두 시점의 국가관심지점정보(국가 POI)를 PostgreSQL/PostGIS에서 비교하여 증분 데이터를 추출하고, 이를 기존 Neo4j 공간지식그래프에 반영하는 파이프라인이다. 전체 재구축(Batch Rebuild)과 증분 갱신(Incremental Update)의 처리 시간 및 논리적 쓰기 연산량을 비교한다.

준비된 연구 DB를 전제로 한 구현이며, 원천 데이터와 DB 설치 및 초기 구축 과정은 공개 범위에 포함하지 않는다.

## 1. 사용한 데이터

### 1.1 T1: 국가관심지점정보

- 시점: 2024년 11월
- 출처: [브이월드](https://www.vworld.kr/v4po_main.do)

### 1.2 T2: 국가관심지점정보

- 시점: 2026년 1월
- 출처: [국토정보플랫폼](https://map.ngii.go.kr/mn/mainPage.do)

### 1.3 행정구역 경계

- 자료: 2025년 센서스 행정구역 경계
- 구분: 전국 시도·시군구·행정동
- 출처: [브이월드](https://www.vworld.kr/v4po_main.do)

실험 범위는 서울특별시이다. 두 시점의 POI에 동일한 행정구역 경계를 적용하고, 공간 포함관계를 이용하여 각 POI의 소속 행정동을 사전 계산한다.

위치 비교에는 EPSG:5179를 사용한다. Neo4j에는 EPSG:4326으로 변환한 좌표를 `point` 형식으로 저장한다.

## 2. 증분 갱신 원리

### 2.1 변화 탐지

두 시점의 POI를 `nf_id` 기준으로 비교한다. 감시 속성(watched properties)은 다음과 같다.

| 감시 속성 | 필드 | 변경 기준 |
| --- | --- | --- |
| 명칭 | `poi_nm` | 값의 차이 |
| 분류코드 | `poi_cl_dc` | 값의 차이 |
| 소속 행정동 | `adm_cd` | 값의 차이 |
| 위치 | `geom` | 이동 거리 1m 초과 |

위치 변경 기준인 1m는 미세한 위치 차이를 갱신 대상에서 제외하기 위한 운영적 허용오차이다. 보편적인 최적 임계값을 의미하지 않는다.

비교 결과에 따라 객체를 네 가지 유형으로 분류한다.

| 유형 | 판정 조건 |
| --- | --- |
| Appear | T1에 없고 T2에 존재하는 ID |
| Updated | 양 시점에 존재하며 감시 속성의 변경 기준에 해당하는 ID |
| Disappear | T1에 존재하고 T2에 없는 ID |
| No Change | 변경 기준에 해당하지 않는 ID |

### 2.2 그래프 반영

공간지식그래프는 다음과 같은 계층으로 구성한다.

```text
POI ──IN──▶ 행정동 ──BELONG_TO──▶ 시군구 ──BELONG_TO──▶ 시도
```

기존 행정구역 계층을 유지하면서 POI 노드와 행정동 사이의 `IN` 관계를 갱신한다.

| 유형 | 갱신 동작 |
| --- | --- |
| Appear | POI 노드를 생성하고 소속 행정동과 IN 관계를 연결한다. |
| Updated | 기존 POI의 속성과 위치를 갱신하고 IN 관계를 재연결한다. |
| Disappear | IN 관계를 제거하고 POI를 POITombstone으로 전환한다. |
| No Change | 기존 T1 상태를 유지한다. |

Disappear 객체는 물리적으로 삭제하지 않는다. 마지막 속성과 위치를 보존하고, 마지막 관측 시점과 최초 미관측 시점을 기록한다.

반면 Batch Rebuild는 기존 POI를 제거한 후 T2 전체를 다시 적재한다.

### 2.3 해석 범위

Appear와 Disappear는 **`nf_id` 기준 신규 관측·미관측**이다. 실제 시설의 개업·폐업을 의미하지 않는다. 동일 시설이 서로 다른 ID로 제공되면 Appear와 Disappear로 분리될 수 있으며, 본 구현에서는 시점 간 동일 시설을 판별하는 Entity Resolution을 수행하지 않는다.

또한 증분 갱신은 No Change 객체의 T1 상태를 유지하므로, 모든 속성과 좌표가 T2와 완전히 동일함을 보장하는 방식은 아니다.

## 3. 코드 설명

### 3.1 Batch 및 증분 갱신

| 파일 | 역할 |
| --- | --- |
| [`benchmark/batch_ops.py`](benchmark/batch_ops.py) | Batch 방식의 POI 제거·전체 적재와 공통 속성 변환을 담당한다. |
| [`benchmark/change_detection.py`](benchmark/change_detection.py) | 두 스냅샷을 비교하고 변경 유형별 증분 데이터를 추출한다. |
| [`benchmark/incremental_ops.py`](benchmark/incremental_ops.py) | 신규·수정 객체 반영과 미관측 객체의 tombstone 전환을 담당한다. |

### 3.2 실행 및 검증

| 파일 | 역할 |
| --- | --- |
| [`benchmark/execution.py`](benchmark/execution.py) | T1 복원, 데이터 전달, 트랜잭션 분할 및 시간 측정을 담당한다. |
| [`benchmark/validation.py`](benchmark/validation.py) | 활성 ID, 감시 속성, 좌표 갱신 정책, IN 관계 및 tombstone을 검증한다. |
| [`benchmark_runner.py`](benchmark_runner.py) | 반복 실행, 측정, 검증 및 결과 저장을 제어하는 공통 실행기이다. |

### 3.3 실험 1·2

| 항목 | 실험 1 | 실험 2 |
| --- | --- | --- |
| 진입점 | [`experiment_1.py`](experiment_1.py) | [`experiment_2.py`](experiment_2.py) |
| 범위 | 서울특별시 전체 | 서울시 25개 자치구 |
| 목적 | Batch와 Incremental의 갱신 성능 비교 | 자치구별 변경률과 시간 절감률의 관계 분석 |
| 트랜잭션 크기 | 최대 1,000 POI | 최대 5,000 POI |
| 본측정 | 방식별 3회 | 자치구별·방식별 3회 |

워밍업은 본측정과 분리하여 수행한다. 각 회차는 대상 범위의 T1을 복원한 상태에서 시작하며, 이전 회차의 갱신 결과를 누적하지 않는다.

시간 측정 범위는 다음과 같다.

- **Batch:** 기존 POI 삭제 및 T2 전체 조회·변환·적재
- **Incremental:** 변경 탐지 및 증분 테이블 생성, 증분 조회·변환·반영
- **공통 제외:** 원천 데이터 전처리, T1 복원 및 사후 정합성 검증

쓰기 연산량은 Neo4j의 논리적 연산 카운터를 사용한다. 물리적 디스크 I/O나 저장공간 사용량을 의미하지 않는다.

세부 실행 흐름은 [`benchmark/README.md`](benchmark/README.md), 측정 및 검증 정의는 [`docs/experiment_design.md`](docs/experiment_design.md)에 정리한다.

## 별첨: 코드 확인 및 실행 안내

- 본 코드는 발표에서 사용한 연구 구현을 확인하기 위한 참고 자료입니다.
- 연결 설정 형식은 [`.env.example`](.env.example), Python 의존성은 [`requirements.txt`](requirements.txt)를 참고해 주세요.
- `--apply` 없이 실행하면 PostgreSQL에서 대상 데이터의 건수만 확인합니다.
- 쓰기 실행 시에는 매 회차 Neo4j의 모든 `POI`·`POITombstone`을 제거하고 대상 범위의 T1을 복원하므로, 전용 실험 DB에서만 실행해 주세요.
