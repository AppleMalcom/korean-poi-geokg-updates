"""실험 2: 서울 25개 자치구의 변경률과 시간 절감률 비교.
발표 조건인 최대 5,000 POI/트랜잭션, 자치구별·방식별 본측정 3회를 실행한다.
워밍업은 별도 파일로 사전 실행했으므로 --skip-warmup을 공통 실행기에 전달한다.
기본은 25개 구 전체이며 --region으로 범위를 제한할 수 있다.
--apply 없이는 건수 확인 후 종료한다. DB는 준비된 연구 환경을 전제로 한다.
"""
import sys

from benchmark_runner import main


def run(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    main(
        argv=["--experiment2", "--skip-warmup", "--batch-size", "5000", *arguments],
        description=__doc__,
    )


if __name__ == "__main__":
    run()
