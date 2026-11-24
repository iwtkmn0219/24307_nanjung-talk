# 인프라 콘솔 작업 체크리스트

리전은 전부 `ap-northeast-2`(서울)다. 아래 값은 고정이다.

## 0. 계정 준비 (첫날)

- [ ] AWS Budgets: 월 USD 20 비용 예산 + 이메일 알림
- [ ] 이후 작업은 루트가 아닌 IAM 사용자로 한다
- [ ] Bedrock 모델 접근 확인: `amazon.titan-embed-text-v2:0`, `global.anthropic.claude-haiku-4-5-20251001-v1:0`

## 1. 네트워크

- [ ] VPC `nanjung-vpc`, CIDR `10.0.0.0/16`
- [ ] 프라이빗 서브넷 2개: `ap-northeast-2a`, `ap-northeast-2c`. **NAT 게이트웨이는 만들지 않는다.**
- [ ] 보안 그룹
  - `sg-lambda`: 인바운드 없음, 아웃바운드 전체
  - `sg-rds`: 인바운드 TCP 5432, 소스 `sg-lambda`만
  - `sg-endpoint`: 인바운드 TCP 443, 소스 `sg-lambda`만
- [ ] VPC 엔드포인트
  - `com.amazonaws.ap-northeast-2.bedrock-runtime`: Interface, Private DNS 켬, 서브넷 2개, `sg-endpoint`
  - `com.amazonaws.ap-northeast-2.s3`: Gateway, 프라이빗 라우팅 테이블
  - `com.amazonaws.ap-northeast-2.dynamodb`: Gateway, 프라이빗 라우팅 테이블

## 2. RDS

- [ ] PostgreSQL 16, `db.t4g.micro`, 스토리지 20GB
- [ ] 퍼블릭 액세스 끔, 서브넷 그룹 = 위 프라이빗 서브넷 2개, 보안 그룹 `sg-rds`
- [ ] 자동 백업 7일
- [ ] 초기 DB 이름 `nanjung`
- [ ] 마스터 사용자와 별도로 앱 사용자 `nanjung_app`을 만들거나, 마스터 사용자를 `DbUser` 파라미터로 넘긴다
- [ ] pgvector 확장은 적재 Lambda의 `init_schema`가 만든다(`CREATE EXTENSION vector` 권한 필요, 마스터 사용자 권장)

## 3. S3

- [ ] 버킷 `nanjung-data-<계정ID>`, 퍼블릭 차단. 접두사 `raw/`, `processed/`

## 4. 배포 전 로컬 준비

- [ ] RDS 인증서 번들을 패키지에 넣는다. RDS 인증서는 Amazon 사설 CA라서 기본 신뢰 저장소로는 검증이 안 된다.
  `https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem` → `src/nanjung/rds-global-bundle.pem`
  (template.yaml의 `DB_SSL_CA`가 `/var/task/nanjung/rds-global-bundle.pem`을 가리킨다)
- [ ] `sam build && sam deploy --guided`
  - 파라미터: `DbHost`(RDS 엔드포인트), `DbPassword`(NoEcho), `SubnetIds`(프라이빗 서브넷 2개), `LambdaSgId`(`sg-lambda`), `DataBucket`

## 5. 데이터 적재

```bash
aws s3 sync data/raw s3://nanjung-data-<id>/raw/
aws lambda invoke --function-name <Ingest> --payload '{"action":"init_schema"}' --cli-binary-format raw-in-base64-out out.json
INGEST_FUNCTION=<Ingest> scripts/ingest_all.sh 0080_010_00[1-7]   # 임진년만, 합계 130
INGEST_FUNCTION=<Ingest> scripts/ingest_all.sh                    # 전부(이미 처리된 달은 processed/ 캐시 사용)
aws lambda invoke --function-name <Ingest> --payload '{"action":"build_today_map"}' --cli-binary-format raw-in-base64-out out.json
```

확인: RDS `diary` 행 수 1,593, DynamoDB `TodayMap` 항목 366.
