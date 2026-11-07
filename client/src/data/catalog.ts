// Hardcoded demo data (synthetic, from the TrustED PETs Proving Ground 2026 package, CC BY 4.0 © Since AI ry).
import type { CatalogEntry } from '@/types/data.types'

/** gold field labels (metadata/field_catalog.csv) for the sample tables */
export const CATALOG: CatalogEntry[] = [
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "visit_id",
  "privacy_role": "record_key",
  "subtype": "RECORD_ID",
  "description": "Visit identifier ED25-NNNNNN"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "patient_hetu",
  "privacy_role": "direct_identifier",
  "subtype": "NATIONAL_ID",
  "description": "Finnish personal identity code (synthetic, individual number 900-999)"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "patient_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Patient name, 'Lastname Given names'"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "date_of_birth",
  "privacy_role": "quasi_identifier",
  "subtype": "BIRTH_DATE",
  "description": "Date of birth"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "sex",
  "privacy_role": "quasi_identifier",
  "subtype": "SEX",
  "description": "M/F"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "phone",
  "privacy_role": "direct_identifier",
  "subtype": "PHONE",
  "description": "Patient mobile phone, mixed formats"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "home_address",
  "privacy_role": "direct_identifier",
  "subtype": "STREET_ADDRESS",
  "description": "Street address"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "postcode",
  "privacy_role": "quasi_identifier",
  "subtype": "POSTCODE",
  "description": "Home postcode (real Southwest Finland postcodes)"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "municipality",
  "privacy_role": "quasi_identifier",
  "subtype": "MUNICIPALITY",
  "description": "Home municipality"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "arrival_ts",
  "privacy_role": "quasi_identifier",
  "subtype": "TIMESTAMP",
  "description": "Arrival time (local)"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "arrival_mode",
  "privacy_role": "quasi_identifier",
  "subtype": "CATEGORY",
  "description": "walk-in / ambulance / helicopter / police"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "ambulance_unit",
  "privacy_role": "quasi_identifier",
  "subtype": "DEVICE_ID",
  "description": "Ambulance unit call sign AU-<base>-NN or MEDHELI-N"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "triage",
  "privacy_role": "sensitive_attribute",
  "subtype": "HEALTH_DATA",
  "description": "Finnish ABCDE triage (A most urgent)"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "chief_complaint",
  "privacy_role": "free_text",
  "subtype": "FREE_TEXT",
  "description": "Short free-text reason for visit (fi/sv/en)"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "icd10_primary",
  "privacy_role": "sensitive_attribute",
  "subtype": "DIAGNOSIS_CODE",
  "description": "Primary ICD-10 diagnosis"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "icd10_secondary",
  "privacy_role": "sensitive_attribute",
  "subtype": "DIAGNOSIS_CODE",
  "description": "Up to two secondary ICD-10 codes, pipe-separated"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "systolic_bp",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Systolic blood pressure mmHg"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "diastolic_bp",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Diastolic blood pressure mmHg"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "heart_rate",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Heart rate /min"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "resp_rate",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Respiratory rate /min"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "temp_c",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Body temperature °C"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "spo2",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Oxygen saturation %"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "pain_nrs",
  "privacy_role": "sensitive_attribute",
  "subtype": "MEASUREMENT",
  "description": "Pain 0-10"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "attending_physician_id",
  "privacy_role": "technical_identifier",
  "subtype": "EMPLOYEE_ID",
  "description": "Staff id of attending physician"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "attending_physician_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Attending physician name"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "discharge_ts",
  "privacy_role": "quasi_identifier",
  "subtype": "TIMESTAMP",
  "description": "Discharge / departure time"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "los_minutes",
  "privacy_role": "sensitive_attribute",
  "subtype": "HEALTH_DATA",
  "description": "Length of stay in minutes"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "disposition",
  "privacy_role": "sensitive_attribute",
  "subtype": "HEALTH_DATA",
  "description": "home / admitted_ward / icu / transfer / died / left_without_being_seen / cancelled_duplicate"
 },
 {
  "dataset": "health",
  "table": "ed_visits",
  "column": "readmit_30d",
  "privacy_role": "sensitive_attribute",
  "subtype": "HEALTH_DATA",
  "description": "1 if the same patient returned within 30 days"
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "customer_id",
  "privacy_role": "record_key",
  "subtype": "CUSTOMER_ID",
  "description": "Bank customer number."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "hetu",
  "privacy_role": "direct_identifier",
  "subtype": "NATIONAL_ID",
  "description": "Finnish personal identity code (synthetic, range 900-999)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "full_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "All given names + surname (KYC)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "birth_date",
  "privacy_role": "quasi_identifier",
  "subtype": "BIRTH_DATE",
  "description": "Date of birth (KYC)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "street_address",
  "privacy_role": "direct_identifier",
  "subtype": "STREET_ADDRESS",
  "description": "Home address incl. apartment."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "postcode",
  "privacy_role": "quasi_identifier",
  "subtype": "POSTCODE",
  "description": "Postcode."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "city",
  "privacy_role": "quasi_identifier",
  "subtype": "MUNICIPALITY",
  "description": "Municipality."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "email",
  "privacy_role": "direct_identifier",
  "subtype": "EMAIL",
  "description": "Personal e-mail (.example)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "phone",
  "privacy_role": "direct_identifier",
  "subtype": "PHONE",
  "description": "Mobile phone (E.164)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "iban",
  "privacy_role": "direct_identifier",
  "subtype": "IBAN",
  "description": "Customer's main account (synthetic, bank id 9xx)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "income_band",
  "privacy_role": "sensitive_attribute",
  "subtype": "FINANCIAL_DATA",
  "description": "Declared annual gross income band."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "occupation",
  "privacy_role": "quasi_identifier",
  "subtype": "OCCUPATION",
  "description": "Occupation group / life situation (KYC)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "employer",
  "privacy_role": "quasi_identifier",
  "subtype": "ORG_NAME",
  "description": "Employer name (KYC)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "pep_flag",
  "privacy_role": "sensitive_attribute",
  "subtype": "OTHER",
  "description": "Politically exposed person (AML)."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "kyc_risk",
  "privacy_role": "sensitive_attribute",
  "subtype": "FINANCIAL_DATA",
  "description": "AML/KYC risk rating."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "account_open_date",
  "privacy_role": "quasi_identifier",
  "subtype": "DATE",
  "description": "Date the customer relationship began."
 },
 {
  "dataset": "finance",
  "table": "customers",
  "column": "preferred_language",
  "privacy_role": "quasi_identifier",
  "subtype": "LANGUAGE",
  "description": "Service language fi/sv/en."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "event_id",
  "privacy_role": "record_key",
  "subtype": "RECORD_ID",
  "description": "Sign-in event id."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "ts_utc",
  "privacy_role": "quasi_identifier",
  "subtype": "TIMESTAMP",
  "description": "Sign-in time (UTC)."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "upn",
  "privacy_role": "direct_identifier",
  "subtype": "USERNAME",
  "description": "Signing-in account."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "src_ip",
  "privacy_role": "technical_identifier",
  "subtype": "IP_ADDRESS",
  "description": "Source IP (CGNAT home/mobile, office, hotel, hosting)."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "geo_country",
  "privacy_role": "quasi_identifier",
  "subtype": "LOCATION_NAME",
  "description": "Country of src_ip (synthetic geo database)."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "geo_city",
  "privacy_role": "quasi_identifier",
  "subtype": "LOCATION_NAME",
  "description": "City of src_ip."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "geo_lat",
  "privacy_role": "quasi_identifier",
  "subtype": "GPS_COORDINATE",
  "description": "City latitude."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "geo_lon",
  "privacy_role": "quasi_identifier",
  "subtype": "GPS_COORDINATE",
  "description": "City longitude."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "user_agent",
  "privacy_role": "technical_identifier",
  "subtype": "USER_AGENT",
  "description": "Client user agent."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "client_app",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "Application signed into."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "device_name",
  "privacy_role": "technical_identifier",
  "subtype": "HOSTNAME",
  "description": "Device name (laptop hostname, kiosk, iPhone/Android)."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "result",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "success / failure / interrupted."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "failure_reason",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "Error code and text."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "mfa_method",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "MFA method."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "mfa_result",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "MFA outcome (approved/denied/pending/timeout)."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "risk_level",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "Identity-protection risk level."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "correlation_id",
  "privacy_role": "technical_identifier",
  "subtype": "RECORD_ID",
  "description": "Random correlation GUID (not linking)."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "attack_label",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "Ground-truth MITRE ATT&CK technique id(s) for synthetic attack events, '|'-separated; empty = benign. Self-assessment only."
 },
 {
  "dataset": "cyber",
  "table": "signin_logs",
  "column": "campaign_id",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "Ground-truth campaign (C1 phishing chain, C2 password spray, C3 insider); empty = benign."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "student_id",
  "privacy_role": "record_key",
  "subtype": "STUDENT_ID",
  "description": "School-system student number; first two digits are the start year."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "learner_id",
  "privacy_role": "direct_identifier",
  "subtype": "STUDENT_ID",
  "description": "National learner number (fictional OID-style format 1.9.999.24.x)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "hetu",
  "privacy_role": "direct_identifier",
  "subtype": "NATIONAL_ID",
  "description": "Finnish personal identity code (temporary range 900-999)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "first_names",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "All given names."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "last_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Surname."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "birth_date",
  "privacy_role": "quasi_identifier",
  "subtype": "BIRTH_DATE",
  "description": "Date of birth."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "sex",
  "privacy_role": "quasi_identifier",
  "subtype": "SEX",
  "description": "Registered sex (M/F)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "home_language",
  "privacy_role": "quasi_identifier",
  "subtype": "LANGUAGE",
  "description": "Registered mother tongue (ISO 639-1)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "street_address",
  "privacy_role": "direct_identifier",
  "subtype": "STREET_ADDRESS",
  "description": "Home street address."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "postcode",
  "privacy_role": "quasi_identifier",
  "subtype": "POSTCODE",
  "description": "Home postcode."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "municipality",
  "privacy_role": "quasi_identifier",
  "subtype": "MUNICIPALITY",
  "description": "Home municipality."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "guardian1_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Guardian name (third party)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "guardian1_phone",
  "privacy_role": "direct_identifier",
  "subtype": "PHONE",
  "description": "Guardian phone, as typed (mixed formats)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "guardian2_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Second guardian name."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "guardian2_phone",
  "privacy_role": "direct_identifier",
  "subtype": "PHONE",
  "description": "Second guardian phone."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "school_code",
  "privacy_role": "quasi_identifier",
  "subtype": "ORG_NAME",
  "description": "School code S01-S12."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "school_name",
  "privacy_role": "quasi_identifier",
  "subtype": "ORG_NAME",
  "description": "School name (fictional)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "programme",
  "privacy_role": "quasi_identifier",
  "subtype": "EDUCATION_DATA",
  "description": "Programme or vocational field."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "class_group",
  "privacy_role": "quasi_identifier",
  "subtype": "EDUCATION_DATA",
  "description": "Homeroom group; encodes school and start year."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "start_date",
  "privacy_role": "quasi_identifier",
  "subtype": "DATE",
  "description": "Start of studies."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "special_support",
  "privacy_role": "sensitive_attribute",
  "subtype": "HEALTH_DATA",
  "description": "Level of special support (none/intensified/special)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "finnish_as_second_language",
  "privacy_role": "sensitive_attribute",
  "subtype": "SOCIAL_DATA",
  "description": "Studies Finnish as a second language (S2)."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "status",
  "privacy_role": "sensitive_attribute",
  "subtype": "EDUCATION_DATA",
  "description": "active / graduated / dropped_out."
 },
 {
  "dataset": "education",
  "table": "students",
  "column": "end_date",
  "privacy_role": "quasi_identifier",
  "subtype": "DATE",
  "description": "Graduation or drop-out date."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "request_id",
  "privacy_role": "record_key",
  "subtype": "RECORD_ID",
  "description": "Request id SR-<year>-<n>; '-D' suffix marks duplicate submissions."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "ts_created",
  "privacy_role": "quasi_identifier",
  "subtype": "TIMESTAMP",
  "description": "Creation time (local)."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "channel",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "web / app / phone / email."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "category",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "Request category (9 classes)."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "language",
  "privacy_role": "quasi_identifier",
  "subtype": "LANGUAGE",
  "description": "Language of the request (fi/sv/en)."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "description",
  "privacy_role": "free_text",
  "subtype": "FREE_TEXT",
  "description": "Citizen's own description. Names of neighbours and relatives, addresses, phone numbers, emails, licence plates, health mentions."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "reporter_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Reporter name (optional)."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "reporter_phone",
  "privacy_role": "direct_identifier",
  "subtype": "PHONE",
  "description": "Reporter phone, as typed."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "reporter_email",
  "privacy_role": "direct_identifier",
  "subtype": "EMAIL",
  "description": "Reporter email."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "reporter_account_id",
  "privacy_role": "technical_identifier",
  "subtype": "ACCOUNT_ID",
  "description": "Persistent e-service account of a logged-in reporter."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "street_address",
  "privacy_role": "quasi_identifier",
  "subtype": "STREET_ADDRESS",
  "description": "Address of the issue (often the reporter's own home or street)."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "postcode",
  "privacy_role": "quasi_identifier",
  "subtype": "POSTCODE",
  "description": "Postcode of the issue location."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "municipality",
  "privacy_role": "non_sensitive",
  "subtype": "MUNICIPALITY",
  "description": "Municipality of the issue location."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "lat",
  "privacy_role": "quasi_identifier",
  "subtype": "GPS_COORDINATE",
  "description": "Latitude of the issue (~25 m precision)."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "lon",
  "privacy_role": "quasi_identifier",
  "subtype": "GPS_COORDINATE",
  "description": "Longitude of the issue."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "handler_name",
  "privacy_role": "direct_identifier",
  "subtype": "PERSON_NAME",
  "description": "Staff member handling the request."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "status",
  "privacy_role": "non_sensitive",
  "subtype": "CATEGORY",
  "description": "closed / in_progress / forwarded / rejected / open."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "ts_closed",
  "privacy_role": "quasi_identifier",
  "subtype": "TIMESTAMP",
  "description": "Closing time."
 },
 {
  "dataset": "public_admin",
  "table": "service_requests",
  "column": "response_text",
  "privacy_role": "free_text",
  "subtype": "FREE_TEXT",
  "description": "City's reply: repeats reporter first name, addresses, plates, handler name/phone/email."
 }
]
