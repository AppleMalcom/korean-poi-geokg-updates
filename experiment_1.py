"""실험 1: 서울 전체 Batch Rebuild와 Incremental Update 비교.
발표 조건인 최대 1,000 POI/트랜잭션, 방식별 본측정 3회를 공통 실행기에 전달한다.
워밍업은 별도 파일로 사전 실행했으며, 이 진입점에는 포함하지 않는다.
--apply 없이는 건수 확인 후 종료한다. DB는 준비된 연구 환경을 전제로 한다.
"""
import sys

from benchmark_runner import main


def run(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    main(
        argv=["--all-seoul", "--experiment1-three", "--batch-size", "1000", *arguments],
        description=__doc__,
    )


if __name__ == "__main__":
    run()
