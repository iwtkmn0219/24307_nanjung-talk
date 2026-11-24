# 인프라 콘솔 작업 체크리스트

리전은 전부 `ap-northeast-2`(서울)다. 아래 값은 고정이다.

## 0. 계정 준비 (첫날)

- [x] AWS Budgets: 월 USD 40 비용 예산(`nanjung-monthly-40`) + 사용자 메일 알림(실제 80%, 예측 100%) — 사용자 결정
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
  - `com.amazonaws.ap-northeast-2.bedrock-runtime`: Interface, Private DNS 켬, **서브넷 1개(2a)만**(비용 절감, 사용자 결정. 2c의 Lambda도 Private DNS로 접근), `sg-endpoint`
  - `com.amazonaws.ap-northeast-2.s3`: Gateway, 프라이빗 라우팅 테이블
  - `com.amazonaws.ap-northeast-2.dynamodb`: Gateway, 프라이빗 라우팅 테이블

## 2. RDS

- [ ] PostgreSQL 16, `db.t4g.micro`, 스토리지 20GB
- [ ] 퍼블릭 액세스 끔, 서브넷 그룹 = 위 프라이빗 서브넷 2개, 보안 그룹 `sg-rds`
- [ ] 자동 백업 1일(무료 플랜 제한, 복구는 S3 processed에서 다시 적재). 7일은 FreeTierRestrictionError로 거부됨
- [ ] 초기 DB 이름 `nanjung`
- [ ] DB 사용자: **MVP는 마스터 사용자를 그대로 쓴다.** `sam deploy` 때 `DbUser`에 마스터 사용자 이름, `DbPassword`에 그 비밀번호를 넘긴다.
  - 이유: 적재 Lambda의 `init_schema`가 `CREATE EXTENSION vector`와 테이블·인덱스를 만든다. RDS에서 확장 설치는 `rds_superuser` 역할(마스터 사용자)이 필요하다.
  - 앱 전용 사용자로 나누려면 스키마를 만든 뒤 마스터로 `CREATE ROLE nanjung_app LOGIN PASSWORD '...'; GRANT SELECT, INSERT, UPDATE ON diary TO nanjung_app;`를 실행하고 `DbUser=nanjung_app`으로 재배포한다(선택).

## 3. S3

- [ ] 버킷 `nanjung-data-<계정ID>`, 퍼블릭 차단. 접두사 `raw/`, `processed/`

## 4. 배포 전 로컬 준비

- [ ] RDS 인증서 번들을 패키지에 넣는다: `bash scripts/fetch_rds_ca.sh`
  - RDS 인증서는 Amazon 사설 CA라서 기본 신뢰 저장소로는 검증이 안 된다. 스크립트가 `https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem`을 `src/nanjung/rds-global-bundle.pem`으로 받고 검사한다(파일은 git에 넣지 않는다).
  - template.yaml의 `DB_SSL_CA`가 `/var/task/nanjung/rds-global-bundle.pem`을 가리킨다. 번들이 없으면 첫 DB 연결에서 실패한다.
- [ ] 배포 직전 검사: `python scripts/predeploy_check.py` → `OK: RDS CA 인증서 N개`가 아니면 배포하지 않는다
- [ ] `sam build && sam deploy --guided`
  - 파라미터: `DbHost`(RDS 엔드포인트), `DbUser`(마스터 사용자 이름), `DbPassword`(NoEcho), `SubnetIds`(프라이빗 서브넷 2개), `LambdaSgId`(`sg-lambda`), `DataBucket`
  - `IngestReservedConcurrency`는 기본 0(예약 안 함)으로 둔다. 계정 동시성 한도가 10인 신규 계정에서는 어떤 예약도 배포를 막는다. 적재는 `ingest_all.sh`가 순차로 호출하므로 예약이 없어도 동시에 돌지 않는다.

## 5. 데이터 적재

```bash
aws s3 sync data/raw s3://nanjung-data-<id>/raw/
aws lambda invoke --function-name <Ingest> --payload '{"action":"init_schema"}' --cli-binary-format raw-in-base64-out out.json
cat out.json            # {"ok": true} 이어야 한다. 명령 출력에 "FunctionError"가 있으면 실패다
INGEST_FUNCTION=<Ingest> bash scripts/ingest_all.sh '0080_010_00[1-7]'   # 임진년만, 합계 130
INGEST_FUNCTION=<Ingest> bash scripts/ingest_all.sh                      # 전부(이미 처리된 달은 processed/ 캐시 사용)
aws lambda invoke --function-name <Ingest> --payload '{"action":"build_today_map"}' --cli-binary-format raw-in-base64-out out.json
cat out.json            # {"count": 366} 이어야 한다. "FunctionError"가 있으면 실패다
```

확인: RDS `diary` 행 수 1,593, DynamoDB `TodayMap` 항목 366.

## 6. 웹 배포 — S3 + CloudFront (Task 12, 실제 생성한 구성)

- 웹 버킷 `nanjung-web-<계정ID>`: 퍼블릭 차단, 정적 호스팅 끔. `web/`만 올린다(`scripts/`·`tests/`는 올리지 않는다).
  - 올리기 전에 `web/config.js`가 `window.API_BASE = "";`인지 확인한다(`git diff web/config.js`가 비어 있어야 한다).
  - `aws s3 sync web s3://<웹 버킷>/ --delete --exclude "fonts/*" --cache-control "public, max-age=300"`
  - `aws s3 sync web/fonts s3://<웹 버킷>/fonts/ --exclude "*.woff2" --cache-control "public, max-age=31536000, immutable"` 후 `fonts.css`만 `max-age=300`으로 다시 올린다(해시 이름이 아님).
  - woff2는 `--content-type font/woff2`로 올린다.
- OAC 1개(`nanjung-web-oac`, sigv4, s3). 버킷 정책은 `cloudfront.amazonaws.com`에게 `s3:GetObject`만 허용하고 `AWS:SourceArn`을 이 배포 ARN으로 제한한다. 직접 S3 URL은 403이다.
- CloudFront 배포(`PriceClass_200`, HTTP/2·3, 기본 루트 `index.html`)
  - 오리진 `web`: 웹 버킷(OAC). 오리진 `api`: HTTP API 도메인(https-only, 읽기 30초)
  - 기본 동작: `web`, redirect-to-https, `Managed-CachingOptimized`, GET·HEAD
  - 동작 `/chat`, `/diary*`: `api`, https-only, 모든 메서드, `Managed-CachingDisabled`, `Managed-AllViewerExceptHostHeader`
  - 관리형 정책 ID는 계정마다 확인한다: `aws cloudfront list-cache-policies --type managed` (CachingDisabled는 `4135ea2d-6df8-44a3-9df3-4b5a84be39ad`)
- 확인 결과: 정적 파일 200, `http://` → 301 `https://`, `/diary`·`/chat` 200, OPTIONS 204, 직접 S3 403, 브라우저에서 `/chat`이 같은 출처로 나감.
- 파일을 고쳐 다시 올린 뒤 바로 반영하려면 `aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"`. 안 해도 5분(max-age=300) 안에 바뀐다.
- `sam deploy`는 `--parameter-overrides`에 없는 파라미터에 이전 값을 쓴다. `SimThreshold=0.22`는 배포 때마다 명시한다.
