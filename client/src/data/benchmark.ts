import type { Benchmark } from '@/types/data.types'

export const BENCHMARK: Benchmark = {
 "customer_service": {
  "B0": {
   "summary": {
    "privacy": 0.2222,
    "utility": 1.0,
    "composite": 0.3438
   },
   "risk_components": {
    "conversations: direct identifiers retained": 0.0,
    "conversations: records with k<5": 1.0,
    "conversations: free-text identifier leakage": 1.0,
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 1.0,
    "customers: linkage re-identification": 0.0,
    "turns: direct identifiers retained": 0.0,
    "turns: records with k<5": 1.0,
    "turns: free-text identifier leakage": 1.0
   },
   "utility": [
    {
     "id": "CS-U1",
     "table": "turns",
     "description": "Intent classifier (TF-IDF + logistic regression) trained on protected train text, tested on original eval text.",
     "required": true,
     "score": 1.0,
     "metric": "macro-F1 ratio (protected-trained / original-trained) on original eval"
    },
    {
     "id": "CS-U2",
     "table": "conversations",
     "description": "Relationship between sentiment and CSAT preserved.",
     "required": true,
     "score": 1.0,
     "metric": "1 - |Δ Spearman(sentiment, CSAT)| / 0.5"
    },
    {
     "id": "CS-U3",
     "table": "conversations",
     "description": "Contact-reason (intent) mix preserved.",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2·TVD of intent distribution"
    },
    {
     "id": "CS-U4",
     "table": "conversations",
     "description": "Average handle time by intent.",
     "required": true,
     "score": 1.0,
     "metric": "mean handle time by intent, MAPE (0.5 → score 0)"
    },
    {
     "id": "CS-U5",
     "table": "turns",
     "description": "Ordinary vocabulary retained in text (redaction should remove identifiers, not meaning).",
     "required": true,
     "score": 1.0,
     "metric": "share of common (non-identifying) word tokens retained, matched by turn_id"
    },
    {
     "id": "CS-U6",
     "table": "conversations",
     "description": "Contact volumes by channel × language.",
     "required": true,
     "score": 1.0,
     "metric": "contacts by channel × language, MAPE"
    },
    {
     "id": "CS-U7",
     "table": "conversations",
     "description": "First-contact resolution rate by intent.",
     "required": true,
     "score": 1.0,
     "metric": "first-contact resolution rate by intent, mean abs. difference (0.2 → score 0)"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.3126,
    "utility": 0.8557,
    "composite": 0.4394
   },
   "risk_components": {
    "conversations: direct identifiers retained": 0.0,
    "conversations: records with k<5": 0.7237,
    "conversations: free-text identifier leakage": 0.8286,
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 1.0,
    "customers: linkage re-identification": 0.0,
    "turns: direct identifiers retained": 0.0,
    "turns: records with k<5": 0.0188,
    "turns: free-text identifier leakage": 0.8012
   },
   "utility": [
    {
     "id": "CS-U1",
     "table": "turns",
     "description": "Intent classifier (TF-IDF + logistic regression) trained on protected train text, tested on original eval text.",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CS-U2",
     "table": "conversations",
     "description": "Relationship between sentiment and CSAT preserved.",
     "required": true,
     "score": 1.0,
     "metric": "1 - |Δ Spearman(sentiment, CSAT)| / 0.5"
    },
    {
     "id": "CS-U3",
     "table": "conversations",
     "description": "Contact-reason (intent) mix preserved.",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2·TVD of intent distribution"
    },
    {
     "id": "CS-U4",
     "table": "conversations",
     "description": "Average handle time by intent.",
     "required": true,
     "score": 1.0,
     "metric": "mean handle time by intent, MAPE (0.5 → score 0)"
    },
    {
     "id": "CS-U5",
     "table": "turns",
     "description": "Ordinary vocabulary retained in text (redaction should remove identifiers, not meaning).",
     "required": true,
     "score": 0.9899,
     "metric": "share of common (non-identifying) word tokens retained, matched by turn_id"
    },
    {
     "id": "CS-U6",
     "table": "conversations",
     "description": "Contact volumes by channel × language.",
     "required": true,
     "score": 1.0,
     "metric": "contacts by channel × language, MAPE"
    },
    {
     "id": "CS-U7",
     "table": "conversations",
     "description": "First-contact resolution rate by intent.",
     "required": true,
     "score": 1.0,
     "metric": "first-contact resolution rate by intent, mean abs. difference (0.2 → score 0)"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.4952,
    "utility": 0.8557,
    "composite": 0.6125
   },
   "risk_components": {
    "conversations: direct identifiers retained": 0.0,
    "conversations: records with k<5": 0.0,
    "conversations: free-text identifier leakage": 0.8286,
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 0.0,
    "customers: linkage re-identification": 0.0,
    "turns: direct identifiers retained": 0.0,
    "turns: records with k<5": 0.0,
    "turns: free-text identifier leakage": 0.8012
   },
   "utility": [
    {
     "id": "CS-U1",
     "table": "turns",
     "description": "Intent classifier (TF-IDF + logistic regression) trained on protected train text, tested on original eval text.",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CS-U2",
     "table": "conversations",
     "description": "Relationship between sentiment and CSAT preserved.",
     "required": true,
     "score": 1.0,
     "metric": "1 - |Δ Spearman(sentiment, CSAT)| / 0.5"
    },
    {
     "id": "CS-U3",
     "table": "conversations",
     "description": "Contact-reason (intent) mix preserved.",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2·TVD of intent distribution"
    },
    {
     "id": "CS-U4",
     "table": "conversations",
     "description": "Average handle time by intent.",
     "required": true,
     "score": 1.0,
     "metric": "mean handle time by intent, MAPE (0.5 → score 0)"
    },
    {
     "id": "CS-U5",
     "table": "turns",
     "description": "Ordinary vocabulary retained in text (redaction should remove identifiers, not meaning).",
     "required": true,
     "score": 0.9899,
     "metric": "share of common (non-identifying) word tokens retained, matched by turn_id"
    },
    {
     "id": "CS-U6",
     "table": "conversations",
     "description": "Contact volumes by channel × language.",
     "required": true,
     "score": 1.0,
     "metric": "contacts by channel × language, MAPE"
    },
    {
     "id": "CS-U7",
     "table": "conversations",
     "description": "First-contact resolution rate by intent.",
     "required": true,
     "score": 1.0,
     "metric": "first-contact resolution rate by intent, mean abs. difference (0.2 → score 0)"
    }
   ]
  }
 },
 "cyber": {
  "B0": {
   "summary": {
    "privacy": 0.2857,
    "utility": 0.3636,
    "composite": 0.3165
   },
   "risk_components": {
    "dns_logs: direct identifiers retained": 0.0,
    "dns_logs: records with k<5": 1.0,
    "edr_alerts: direct identifiers retained": 0.0,
    "edr_alerts: hashed ids reversible": 0.0,
    "edr_alerts: records with k<5": 1.0,
    "email_gateway: direct identifiers retained": 0.0,
    "email_gateway: records with k<5": 1.0,
    "geoip_ranges: direct identifiers retained": 0.0,
    "identity: direct identifiers retained": 0.0,
    "identity: records with k<5": 1.0,
    "identity: linkage re-identification": 0.0,
    "incident_tickets: direct identifiers retained": 0.0,
    "incident_tickets: records with k<5": 1.0,
    "incident_tickets: free-text identifier leakage": 1.0,
    "proxy_logs: direct identifiers retained": 0.0,
    "proxy_logs: records with k<5": 1.0,
    "signin_logs: direct identifiers retained": 0.0,
    "signin_logs: records with k<5": 0.9999,
    "signin_logs: linkage re-identification": 0.0,
    "vpn_logs: direct identifiers retained": 0.0,
    "vpn_logs: records with k<5": 1.0
   },
   "utility": [
    {
     "id": "CYBER-U1",
     "table": "signin_logs",
     "description": "Impossible-travel detection on sign-ins (reference rule, F1 vs labels T1078.004/T1621).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U2",
     "table": "signin_logs",
     "description": "MFA-fatigue detection: >=5 denied pushes in 30 min then approval (labels T1621).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U3",
     "table": "signin_logs",
     "description": "Password-spray detection: failures from one /24 against >=10 accounts per hour (T1110.003).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U4",
     "table": "proxy_logs",
     "description": "Exfiltration detection: >1 GB uploaded from one source to one domain within 4 h (T1567.002).",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, exfiltration volume"
    },
    {
     "id": "CYBER-U5",
     "table": "email_gateway+proxy_logs",
     "description": "Phishing chain: bulk mail from a rare domain followed by recipients' clicks (needs consistent user pseudonyms across e-mail and proxy).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U6",
     "table": "vpn_logs+edr_alerts",
     "description": "Lateral movement: VPN from a never-seen country followed by server alerts within 24 h.",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U7",
     "table": "proxy_logs+edr_alerts",
     "description": "Insider: per-user daily intranet downloads > 4x own median (and >=100) plus removable-media alerts.",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U8",
     "table": "*",
     "description": "Indicators of compromise (attacker IPs, phishing domain, attacker device, tool user agents) kept verbatim for sharing.",
     "required": true,
     "score": 1.0,
     "metric": "share of attacker IoCs kept verbatim"
    },
    {
     "id": "CYBER-U9",
     "table": "*",
     "description": "Cross-log join consistency of user identifiers (keyed pseudonyms pass, random tokens fail).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U10",
     "table": "signin_logs",
     "description": "Sign-in volume by hour (capacity / anomaly baselines).",
     "required": true,
     "score": 1.0,
     "metric": "1 - TVD of hourly sign-in volume"
    },
    {
     "id": "CYBER-U11",
     "table": "edr_alerts",
     "description": "Alert triage statistics: distribution of rule x verdict x severity.",
     "required": true,
     "score": 1.0,
     "metric": "1 - TVD of (rule, verdict, severity) distribution"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.428,
    "utility": 0.7404,
    "composite": 0.5296
   },
   "risk_components": {
    "dns_logs: direct identifiers retained": 0.0,
    "dns_logs: records with k<5": 0.025,
    "edr_alerts: direct identifiers retained": 0.0,
    "edr_alerts: hashed ids reversible": 0.0,
    "edr_alerts: records with k<5": 0.5112,
    "email_gateway: direct identifiers retained": 0.0,
    "email_gateway: records with k<5": 0.0,
    "geoip_ranges: direct identifiers retained": 0.0,
    "identity: direct identifiers retained": 0.0,
    "identity: records with k<5": 1.0,
    "identity: linkage re-identification": 0.0,
    "incident_tickets: direct identifiers retained": 0.0,
    "incident_tickets: records with k<5": 0.5619,
    "incident_tickets: free-text identifier leakage": 0.8173,
    "proxy_logs: direct identifiers retained": 0.0,
    "proxy_logs: records with k<5": 0.0146,
    "signin_logs: direct identifiers retained": 0.0,
    "signin_logs: records with k<5": 0.0313,
    "signin_logs: linkage re-identification": 0.0,
    "vpn_logs: direct identifiers retained": 0.0,
    "vpn_logs: records with k<5": 0.061
   },
   "utility": [
    {
     "id": "CYBER-U1",
     "table": "signin_logs",
     "description": "Impossible-travel detection on sign-ins (reference rule, F1 vs labels T1078.004/T1621).",
     "required": true,
     "score": 0.987,
     "metric": "F1 ratio, impossible travel"
    },
    {
     "id": "CYBER-U2",
     "table": "signin_logs",
     "description": "MFA-fatigue detection: >=5 denied pushes in 30 min then approval (labels T1621).",
     "required": true,
     "score": 0.8571,
     "metric": "F1 ratio, MFA fatigue"
    },
    {
     "id": "CYBER-U3",
     "table": "signin_logs",
     "description": "Password-spray detection: failures from one /24 against >=10 accounts per hour (T1110.003).",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, password spray"
    },
    {
     "id": "CYBER-U4",
     "table": "proxy_logs",
     "description": "Exfiltration detection: >1 GB uploaded from one source to one domain within 4 h (T1567.002).",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, exfiltration volume"
    },
    {
     "id": "CYBER-U5",
     "table": "email_gateway+proxy_logs",
     "description": "Phishing chain: bulk mail from a rare domain followed by recipients' clicks (needs consistent user pseudonyms across e-mail and proxy).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U6",
     "table": "vpn_logs+edr_alerts",
     "description": "Lateral movement: VPN from a never-seen country followed by server alerts within 24 h.",
     "required": true,
     "score": 0.25,
     "metric": "F1 ratio, foreign VPN -> server alerts (lateral movement)"
    },
    {
     "id": "CYBER-U7",
     "table": "proxy_logs+edr_alerts",
     "description": "Insider: per-user daily intranet downloads > 4x own median (and >=100) plus removable-media alerts.",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, insider bulk download / removable media"
    },
    {
     "id": "CYBER-U8",
     "table": "*",
     "description": "Indicators of compromise (attacker IPs, phishing domain, attacker device, tool user agents) kept verbatim for sharing.",
     "required": true,
     "score": 0.05,
     "metric": "share of attacker IoCs kept verbatim"
    },
    {
     "id": "CYBER-U9",
     "table": "*",
     "description": "Cross-log join consistency of user identifiers (keyed pseudonyms pass, random tokens fail).",
     "required": true,
     "score": 1.0,
     "metric": "same user -> same pseudonym across tables x different users -> different pseudonyms"
    },
    {
     "id": "CYBER-U10",
     "table": "signin_logs",
     "description": "Sign-in volume by hour (capacity / anomaly baselines).",
     "required": true,
     "score": 1.0,
     "metric": "1 - TVD of hourly sign-in volume"
    },
    {
     "id": "CYBER-U11",
     "table": "edr_alerts",
     "description": "Alert triage statistics: distribution of rule x verdict x severity.",
     "required": true,
     "score": 1.0,
     "metric": "1 - TVD of (rule, verdict, severity) distribution"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.5719,
    "utility": 0.6955,
    "composite": 0.6221
   },
   "risk_components": {
    "dns_logs: direct identifiers retained": 0.0,
    "dns_logs: records with k<5": 0.0,
    "edr_alerts: direct identifiers retained": 0.0,
    "edr_alerts: hashed ids reversible": 0.0,
    "edr_alerts: records with k<5": 0.0,
    "email_gateway: direct identifiers retained": 0.0,
    "email_gateway: records with k<5": 0.0,
    "geoip_ranges: direct identifiers retained": 0.0,
    "identity: direct identifiers retained": 0.0,
    "identity: records with k<5": 0.0,
    "identity: linkage re-identification": 0.0,
    "incident_tickets: direct identifiers retained": 0.0,
    "incident_tickets: records with k<5": 0.0,
    "incident_tickets: free-text identifier leakage": 0.8173,
    "proxy_logs: direct identifiers retained": 0.0,
    "proxy_logs: records with k<5": 0.0,
    "signin_logs: direct identifiers retained": 0.0,
    "signin_logs: records with k<5": 0.0001,
    "signin_logs: linkage re-identification": 0.0,
    "vpn_logs: direct identifiers retained": 0.0,
    "vpn_logs: records with k<5": 0.0
   },
   "utility": [
    {
     "id": "CYBER-U1",
     "table": "signin_logs",
     "description": "Impossible-travel detection on sign-ins (reference rule, F1 vs labels T1078.004/T1621).",
     "required": true,
     "score": 0.76,
     "metric": "F1 ratio, impossible travel"
    },
    {
     "id": "CYBER-U2",
     "table": "signin_logs",
     "description": "MFA-fatigue detection: >=5 denied pushes in 30 min then approval (labels T1621).",
     "required": true,
     "score": 0.8571,
     "metric": "F1 ratio, MFA fatigue"
    },
    {
     "id": "CYBER-U3",
     "table": "signin_logs",
     "description": "Password-spray detection: failures from one /24 against >=10 accounts per hour (T1110.003).",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, password spray"
    },
    {
     "id": "CYBER-U4",
     "table": "proxy_logs",
     "description": "Exfiltration detection: >1 GB uploaded from one source to one domain within 4 h (T1567.002).",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, exfiltration volume"
    },
    {
     "id": "CYBER-U5",
     "table": "email_gateway+proxy_logs",
     "description": "Phishing chain: bulk mail from a rare domain followed by recipients' clicks (needs consistent user pseudonyms across e-mail and proxy).",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CYBER-U6",
     "table": "vpn_logs+edr_alerts",
     "description": "Lateral movement: VPN from a never-seen country followed by server alerts within 24 h.",
     "required": true,
     "score": 0.0,
     "metric": "F1 ratio, foreign VPN -> server alerts (lateral movement)"
    },
    {
     "id": "CYBER-U7",
     "table": "proxy_logs+edr_alerts",
     "description": "Insider: per-user daily intranet downloads > 4x own median (and >=100) plus removable-media alerts.",
     "required": true,
     "score": 1.0,
     "metric": "F1 ratio, insider bulk download / removable media"
    },
    {
     "id": "CYBER-U8",
     "table": "*",
     "description": "Indicators of compromise (attacker IPs, phishing domain, attacker device, tool user agents) kept verbatim for sharing.",
     "required": true,
     "score": 0.05,
     "metric": "share of attacker IoCs kept verbatim"
    },
    {
     "id": "CYBER-U9",
     "table": "*",
     "description": "Cross-log join consistency of user identifiers (keyed pseudonyms pass, random tokens fail).",
     "required": true,
     "score": 1.0,
     "metric": "same user -> same pseudonym across tables x different users -> different pseudonyms"
    },
    {
     "id": "CYBER-U10",
     "table": "signin_logs",
     "description": "Sign-in volume by hour (capacity / anomaly baselines).",
     "required": true,
     "score": 0.9831,
     "metric": "1 - TVD of hourly sign-in volume"
    },
    {
     "id": "CYBER-U11",
     "table": "edr_alerts",
     "description": "Alert triage statistics: distribution of rule x verdict x severity.",
     "required": true,
     "score": 1.0,
     "metric": "1 - TVD of (rule, verdict, severity) distribution"
    }
   ]
  }
 },
 "education": {
  "B0": {
   "summary": {
    "privacy": 0.3839,
    "utility": 1.0,
    "composite": 0.5333
   },
   "risk_components": {
    "absences: direct identifiers retained": 0.0,
    "absences: records with k<5": 0.0,
    "counsellor_notes: direct identifiers retained": 0.0,
    "counsellor_notes: records with k<5": 0.2618,
    "counsellor_notes: free-text identifier leakage": 1.0,
    "course_grades: direct identifiers retained": 0.0,
    "course_grades: records with k<5": 0.511,
    "matriculation_results: direct identifiers retained": 0.0,
    "matriculation_results: records with k<5": 0.0125,
    "students: direct identifiers retained": 0.0,
    "students: records with k<5": 1.0,
    "students: linkage re-identification": 0.0
   },
   "utility": [
    {
     "id": "EDU-U1",
     "table": "course_grades",
     "description": "Mean grade (4-10 scale) by school x subject",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAE of mean grade per (school, subject) / 1 grade"
    },
    {
     "id": "EDU-U2",
     "table": "students",
     "description": "Drop-out prediction AUC: train on protected, test on original hold-out",
     "required": true,
     "score": 1.0,
     "metric": "AUC retention (train protected, test original)"
    },
    {
     "id": "EDU-U3",
     "table": "course_grades",
     "description": "Gender gap in maths module grades",
     "required": true,
     "score": 1.0,
     "metric": "1 - |gap error| / 0.3 grade (gap = mean F - mean M, maths modules)"
    },
    {
     "id": "EDU-U4",
     "table": "absences",
     "description": "Spearman correlation of unexcused absence hours with mean grade",
     "required": true,
     "score": 1.0,
     "metric": "1 - |Spearman r error| / 0.3"
    },
    {
     "id": "EDU-U5",
     "table": "matriculation_results",
     "description": "Matriculation grade distribution by subject",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean TVD of grade distribution per subject / 0.3"
    },
    {
     "id": "EDU-U6",
     "table": "students",
     "description": "Drop-out rate by programme",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean abs error of drop-out rate per programme / 0.10"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.3894,
    "utility": 0.7654,
    "composite": 0.5014
   },
   "risk_components": {
    "absences: direct identifiers retained": 0.0,
    "absences: records with k<5": 0.0,
    "counsellor_notes: direct identifiers retained": 0.0,
    "counsellor_notes: records with k<5": 0.2618,
    "counsellor_notes: free-text identifier leakage": 0.8809,
    "course_grades: direct identifiers retained": 0.0,
    "course_grades: records with k<5": 0.511,
    "matriculation_results: direct identifiers retained": 0.0,
    "matriculation_results: records with k<5": 0.0002,
    "students: direct identifiers retained": 0.0,
    "students: records with k<5": 1.0,
    "students: linkage re-identification": 0.0
   },
   "utility": [
    {
     "id": "EDU-U1",
     "table": "course_grades",
     "description": "Mean grade (4-10 scale) by school x subject",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAE of mean grade per (school, subject) / 1 grade"
    },
    {
     "id": "EDU-U2",
     "table": "students",
     "description": "Drop-out prediction AUC: train on protected, test on original hold-out",
     "required": true,
     "score": 0.5924,
     "metric": "AUC retention (train protected, test original)"
    },
    {
     "id": "EDU-U3",
     "table": "course_grades",
     "description": "Gender gap in maths module grades",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "EDU-U4",
     "table": "absences",
     "description": "Spearman correlation of unexcused absence hours with mean grade",
     "required": true,
     "score": 1.0,
     "metric": "1 - |Spearman r error| / 0.3"
    },
    {
     "id": "EDU-U5",
     "table": "matriculation_results",
     "description": "Matriculation grade distribution by subject",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean TVD of grade distribution per subject / 0.3"
    },
    {
     "id": "EDU-U6",
     "table": "students",
     "description": "Drop-out rate by programme",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean abs error of drop-out rate per programme / 0.10"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.5228,
    "utility": 0.7338,
    "composite": 0.6014
   },
   "risk_components": {
    "absences: direct identifiers retained": 0.0,
    "absences: records with k<5": 0.0,
    "counsellor_notes: direct identifiers retained": 0.0,
    "counsellor_notes: records with k<5": 0.0,
    "counsellor_notes: free-text identifier leakage": 0.8809,
    "course_grades: direct identifiers retained": 0.0,
    "course_grades: records with k<5": 0.0,
    "matriculation_results: direct identifiers retained": 0.0,
    "matriculation_results: records with k<5": 0.0002,
    "students: direct identifiers retained": 0.0,
    "students: records with k<5": 0.0,
    "students: linkage re-identification": 0.0
   },
   "utility": [
    {
     "id": "EDU-U1",
     "table": "course_grades",
     "description": "Mean grade (4-10 scale) by school x subject",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAE of mean grade per (school, subject) / 1 grade"
    },
    {
     "id": "EDU-U2",
     "table": "students",
     "description": "Drop-out prediction AUC: train on protected, test on original hold-out",
     "required": true,
     "score": 0.5802,
     "metric": "AUC retention (train protected, test original)"
    },
    {
     "id": "EDU-U3",
     "table": "course_grades",
     "description": "Gender gap in maths module grades",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "EDU-U4",
     "table": "absences",
     "description": "Spearman correlation of unexcused absence hours with mean grade",
     "required": true,
     "score": 1.0,
     "metric": "1 - |Spearman r error| / 0.3"
    },
    {
     "id": "EDU-U5",
     "table": "matriculation_results",
     "description": "Matriculation grade distribution by subject",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean TVD of grade distribution per subject / 0.3"
    },
    {
     "id": "EDU-U6",
     "table": "students",
     "description": "Drop-out rate by programme",
     "required": true,
     "score": 0.8225,
     "metric": "1 - mean abs error of drop-out rate per programme / 0.10"
    }
   ]
  }
 },
 "energy": {
  "B0": {
   "summary": {
    "privacy": 0.3545,
    "utility": 1.0,
    "composite": 0.5017
   },
   "risk_components": {
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 1.0,
    "customers: linkage re-identification": 0.037,
    "customers: free-text identifier leakage": 1.0,
    "meter_readings_hourly: direct identifiers retained": 0.0,
    "meter_readings_hourly: records with k<5": 0.0,
    "weather_hourly: direct identifiers retained": 0.0
   },
   "utility": [
    {
     "id": "ENERGY-U1",
     "table": "meter_readings_hourly",
     "description": "Mean load per 3-digit postcode area × hour of day",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of mean kWh per postcode area x hour"
    },
    {
     "id": "ENERGY-U2",
     "table": "meter_readings_hourly",
     "description": "System peak hours (top 50) and daily peak hour",
     "required": true,
     "score": 1.0,
     "metric": "0.5*Jaccard(top-50 peak hours) + 0.5*share of days with daily peak hour within ±1 h"
    },
    {
     "id": "ENERGY-U3",
     "table": "meter_readings_hourly",
     "description": "Temperature sensitivity (kWh/day per °C) by heating type",
     "required": true,
     "score": 1.0,
     "metric": "mean over heating types of 1 - rel.error/0.5 of kWh-per-°C slope"
    },
    {
     "id": "ENERGY-U4",
     "table": "meter_readings_hourly",
     "description": "Heating-type classifier: train on protected, test on original",
     "required": true,
     "score": 1.0,
     "metric": "min(acc train-protected/test-original, 5-fold CV acc within protected) / 5-fold CV acc on original"
    },
    {
     "id": "ENERGY-U5",
     "table": "meter_readings_hourly",
     "description": "Weekday load-profile clusters (k=5) agreement",
     "required": true,
     "score": 1.0,
     "metric": "0.5*(1 - matched centroid distance / centroid spread) + 0.5*(1 - TVD of cluster sizes), k=5"
    },
    {
     "id": "ENERGY-U6",
     "table": "meter_readings_hourly",
     "description": "Day-ahead forecast of mean load per meter",
     "required": true,
     "score": 1.0,
     "metric": "MAPE(model trained on original) / MAPE(model trained on protected), tested on original 15-28 Feb"
    },
    {
     "id": "ENERGY-U7",
     "table": "customers",
     "description": "Winter consumption by late-payment group × electric heating",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of daily kWh by late-payment group x electric heating"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.4008,
    "utility": 0.9521,
    "composite": 0.544
   },
   "risk_components": {
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 1.0,
    "customers: linkage re-identification": 0.0,
    "customers: free-text identifier leakage": 0.3889,
    "meter_readings_hourly: direct identifiers retained": 0.0,
    "meter_readings_hourly: records with k<5": 0.0,
    "weather_hourly: direct identifiers retained": 0.0
   },
   "utility": [
    {
     "id": "ENERGY-U1",
     "table": "meter_readings_hourly",
     "description": "Mean load per 3-digit postcode area × hour of day",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of mean kWh per postcode area x hour"
    },
    {
     "id": "ENERGY-U2",
     "table": "meter_readings_hourly",
     "description": "System peak hours (top 50) and daily peak hour",
     "required": true,
     "score": 1.0,
     "metric": "0.5*Jaccard(top-50 peak hours) + 0.5*share of days with daily peak hour within ±1 h"
    },
    {
     "id": "ENERGY-U3",
     "table": "meter_readings_hourly",
     "description": "Temperature sensitivity (kWh/day per °C) by heating type",
     "required": true,
     "score": 1.0,
     "metric": "mean over heating types of 1 - rel.error/0.5 of kWh-per-°C slope"
    },
    {
     "id": "ENERGY-U4",
     "table": "meter_readings_hourly",
     "description": "Heating-type classifier: train on protected, test on original",
     "required": true,
     "score": 0.996,
     "metric": "min(acc train-protected/test-original, 5-fold CV acc within protected) / 5-fold CV acc on original"
    },
    {
     "id": "ENERGY-U5",
     "table": "meter_readings_hourly",
     "description": "Weekday load-profile clusters (k=5) agreement",
     "required": true,
     "score": 0.6687,
     "metric": "0.5*(1 - matched centroid distance / centroid spread) + 0.5*(1 - TVD of cluster sizes), k=5"
    },
    {
     "id": "ENERGY-U6",
     "table": "meter_readings_hourly",
     "description": "Day-ahead forecast of mean load per meter",
     "required": true,
     "score": 1.0,
     "metric": "MAPE(model trained on original) / MAPE(model trained on protected), tested on original 15-28 Feb"
    },
    {
     "id": "ENERGY-U7",
     "table": "customers",
     "description": "Winter consumption by late-payment group × electric heating",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of daily kWh by late-payment group x electric heating"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.7774,
    "utility": 0.8351,
    "composite": 0.8026
   },
   "risk_components": {
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 0.0053,
    "customers: linkage re-identification": 0.0,
    "customers: free-text identifier leakage": 0.3889,
    "meter_readings_hourly: direct identifiers retained": 0.0,
    "meter_readings_hourly: records with k<5": 0.0,
    "weather_hourly: direct identifiers retained": 0.0
   },
   "utility": [
    {
     "id": "ENERGY-U1",
     "table": "meter_readings_hourly",
     "description": "Mean load per 3-digit postcode area × hour of day",
     "required": true,
     "score": 0.1835,
     "metric": "1 - MAPE/0.5 of mean kWh per postcode area x hour"
    },
    {
     "id": "ENERGY-U2",
     "table": "meter_readings_hourly",
     "description": "System peak hours (top 50) and daily peak hour",
     "required": true,
     "score": 1.0,
     "metric": "0.5*Jaccard(top-50 peak hours) + 0.5*share of days with daily peak hour within ±1 h"
    },
    {
     "id": "ENERGY-U3",
     "table": "meter_readings_hourly",
     "description": "Temperature sensitivity (kWh/day per °C) by heating type",
     "required": true,
     "score": 0.9955,
     "metric": "mean over heating types of 1 - rel.error/0.5 of kWh-per-°C slope"
    },
    {
     "id": "ENERGY-U4",
     "table": "meter_readings_hourly",
     "description": "Heating-type classifier: train on protected, test on original",
     "required": true,
     "score": 1.0,
     "metric": "min(acc train-protected/test-original, 5-fold CV acc within protected) / 5-fold CV acc on original"
    },
    {
     "id": "ENERGY-U5",
     "table": "meter_readings_hourly",
     "description": "Weekday load-profile clusters (k=5) agreement",
     "required": true,
     "score": 0.6687,
     "metric": "0.5*(1 - matched centroid distance / centroid spread) + 0.5*(1 - TVD of cluster sizes), k=5"
    },
    {
     "id": "ENERGY-U6",
     "table": "meter_readings_hourly",
     "description": "Day-ahead forecast of mean load per meter",
     "required": true,
     "score": 1.0,
     "metric": "MAPE(model trained on original) / MAPE(model trained on protected), tested on original 15-28 Feb"
    },
    {
     "id": "ENERGY-U7",
     "table": "customers",
     "description": "Winter consumption by late-payment group × electric heating",
     "required": true,
     "score": 0.9981,
     "metric": "1 - MAPE/0.5 of daily kWh by late-payment group x electric heating"
    }
   ]
  }
 },
 "finance": {
  "B0": {
   "summary": {
    "privacy": 0.2367,
    "utility": 0.4686,
    "composite": 0.3054
   },
   "risk_components": {
    "card_transactions: direct identifiers retained": 0.0,
    "card_transactions: records with k<5": 1.0,
    "card_transactions: linkage re-identification": 0.7918,
    "cards: direct identifiers retained": 0.0,
    "cards: records with k<5": 1.0,
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 1.0,
    "customers: linkage re-identification": 0.0,
    "transfers: direct identifiers retained": 0.0,
    "transfers: records with k<5": 1.0,
    "transfers: free-text identifier leakage": 1.0
   },
   "utility": [
    {
     "id": "FIN-U1",
     "table": "card_transactions",
     "description": "Fraud model: train on protected Jul–Oct, test on original Nov–Dec (PR-AUC ratio)",
     "required": true,
     "score": 0.8118,
     "metric": "PR-AUC(train protected Jul-Oct, test original Nov-Dec) / PR-AUC(train original)"
    },
    {
     "id": "FIN-U2",
     "table": "card_transactions",
     "description": "Spend by MCC group × merchant city × month",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of spend by MCC group × city × month (cells ≥ 1,000 €)"
    },
    {
     "id": "FIN-U3",
     "table": "card_transactions",
     "description": "Payday effect: spend by day of month",
     "required": true,
     "score": 1.0,
     "metric": "0.5*corr(spend per day of month) + 0.5*(1 - rel.error of payday uplift (15-17 vs 10-12))"
    },
    {
     "id": "FIN-U4",
     "table": "card_transactions",
     "description": "Card spending-profile segmentation (k=6) agreement",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "FIN-U5",
     "table": "transfers",
     "description": "AML rule hits (structuring, rapid pass-through)",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "FIN-U6",
     "table": "customers",
     "description": "Mean monthly card spend by income band × age band",
     "required": true,
     "score": null,
     "metric": "not answerable"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.2864,
    "utility": 0.8327,
    "composite": 0.4081
   },
   "risk_components": {
    "card_transactions: direct identifiers retained": 0.0,
    "card_transactions: records with k<5": 0.9948,
    "card_transactions: linkage re-identification": 0.0,
    "cards: direct identifiers retained": 0.0,
    "cards: records with k<5": 1.0,
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 0.9946,
    "customers: linkage re-identification": 0.0,
    "transfers: direct identifiers retained": 0.0,
    "transfers: records with k<5": 0.9957,
    "transfers: free-text identifier leakage": 0.7143
   },
   "utility": [
    {
     "id": "FIN-U1",
     "table": "card_transactions",
     "description": "Fraud model: train on protected Jul–Oct, test on original Nov–Dec (PR-AUC ratio)",
     "required": true,
     "score": 1.0,
     "metric": "PR-AUC(train protected Jul-Oct, test original Nov-Dec) / PR-AUC(train original)"
    },
    {
     "id": "FIN-U2",
     "table": "card_transactions",
     "description": "Spend by MCC group × merchant city × month",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of spend by MCC group × city × month (cells ≥ 1,000 €)"
    },
    {
     "id": "FIN-U3",
     "table": "card_transactions",
     "description": "Payday effect: spend by day of month",
     "required": true,
     "score": 1.0,
     "metric": "0.5*corr(spend per day of month) + 0.5*(1 - rel.error of payday uplift (15-17 vs 10-12))"
    },
    {
     "id": "FIN-U4",
     "table": "card_transactions",
     "description": "Card spending-profile segmentation (k=6) agreement",
     "required": true,
     "score": 0.996,
     "metric": "cluster agreement of card spending profiles (k=6)"
    },
    {
     "id": "FIN-U5",
     "table": "transfers",
     "description": "AML rule hits (structuring, rapid pass-through)",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean relative error of flagged-account counts per AML rule (structuring, pass-through)"
    },
    {
     "id": "FIN-U6",
     "table": "customers",
     "description": "Mean monthly card spend by income band × age band",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 of mean monthly card spend by income band × age band (20 y)"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.6104,
    "utility": 0.1658,
    "composite": 0.2751
   },
   "risk_components": {
    "card_transactions: direct identifiers retained": 0.0,
    "card_transactions: records with k<5": 0.0,
    "card_transactions: linkage re-identification": 0.0,
    "cards: direct identifiers retained": 0.0,
    "cards: records with k<5": 0.0,
    "customers: direct identifiers retained": 0.0,
    "customers: records with k<5": 0.0006,
    "customers: linkage re-identification": 0.0,
    "transfers: direct identifiers retained": 0.0,
    "transfers: records with k<5": 0.0,
    "transfers: free-text identifier leakage": 0.7143
   },
   "utility": [
    {
     "id": "FIN-U1",
     "table": "card_transactions",
     "description": "Fraud model: train on protected Jul–Oct, test on original Nov–Dec (PR-AUC ratio)",
     "required": true,
     "score": 0.1237,
     "metric": "PR-AUC(train protected Jul-Oct, test original Nov-Dec) / PR-AUC(train original)"
    },
    {
     "id": "FIN-U2",
     "table": "card_transactions",
     "description": "Spend by MCC group × merchant city × month",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 of spend by MCC group × city × month (cells ≥ 1,000 €)"
    },
    {
     "id": "FIN-U3",
     "table": "card_transactions",
     "description": "Payday effect: spend by day of month",
     "required": true,
     "score": 0.5787,
     "metric": "0.5*corr(spend per day of month) + 0.5*(1 - rel.error of payday uplift (15-17 vs 10-12))"
    },
    {
     "id": "FIN-U4",
     "table": "card_transactions",
     "description": "Card spending-profile segmentation (k=6) agreement",
     "required": true,
     "score": 0.2926,
     "metric": "cluster agreement of card spending profiles (k=6)"
    },
    {
     "id": "FIN-U5",
     "table": "transfers",
     "description": "AML rule hits (structuring, rapid pass-through)",
     "required": true,
     "score": 0.0,
     "metric": "1 - mean relative error of flagged-account counts per AML rule (structuring, pass-through)"
    },
    {
     "id": "FIN-U6",
     "table": "customers",
     "description": "Mean monthly card spend by income band × age band",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 of mean monthly card spend by income band × age band (20 y)"
    }
   ]
  }
 },
 "health": {
  "B0": {
   "summary": {
    "privacy": 0.284,
    "utility": 1.0,
    "composite": 0.4211
   },
   "risk_components": {
    "clinical_notes: direct identifiers retained": 0.0,
    "clinical_notes: records with k<5": 1.0,
    "clinical_notes: free-text identifier leakage": 1.0,
    "ed_visits: direct identifiers retained": 0.0,
    "ed_visits: records with k<5": 1.0,
    "ed_visits: linkage re-identification": 0.095,
    "ed_visits: free-text identifier leakage": 0.0,
    "lab_results: direct identifiers retained": 0.0,
    "lab_results: records with k<5": 0.9988,
    "published_weekly_stats: direct identifiers retained": 0.0,
    "published_weekly_stats: records with k<5": 0.6573
   },
   "utility": [
    {
     "id": "H-U1",
     "table": "ed_visits",
     "description": "Weekly influenza-like-illness visits by 10-year age band",
     "required": true,
     "score": 1.0,
     "metric": "MAPE of weekly ILI counts by age band (cells >=3)"
    },
    {
     "id": "H-U2",
     "table": "ed_visits",
     "description": "Median length of stay by triage level",
     "required": true,
     "score": 1.0,
     "metric": "mean relative error of median LOS by triage"
    },
    {
     "id": "H-U3",
     "table": "ed_visits",
     "description": "Admission prediction: train on protected, test on original/holdout (AUC ratio)",
     "required": true,
     "score": 1.0,
     "metric": "(AUC_protected-0.5)/(AUC_original-0.5), train on X, test on original"
    },
    {
     "id": "H-U4",
     "table": "ed_visits",
     "description": "Diagnosis-group mix in the eight largest municipalities",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean TVD/0.15 of diagnosis-group mix in top-8 municipalities"
    },
    {
     "id": "H-U5",
     "table": "ed_visits",
     "description": "Distributions of systolic BP, heart rate, temperature and SpO2",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean Wasserstein distance / IQR over 4 vitals"
    },
    {
     "id": "H-U6",
     "table": "ed_visits",
     "description": "30-day revisit rate by age band (needs readmit_30d or a consistent patient pseudonym)",
     "required": true,
     "score": 1.0,
     "metric": "mean |revisit rate diff| by age band / overall rate"
    },
    {
     "id": "H-U7",
     "table": "lab_results",
     "description": "CRP vs temperature relationship and CRP by diagnosis group (needs visit join)",
     "required": true,
     "score": 1.0,
     "metric": "Spearman(CRP, temp) difference + CRP median by diagnosis group (log scale)"
    },
    {
     "id": "H-U8",
     "table": "ed_visits",
     "description": "Hour-of-day arrival curve",
     "required": true,
     "score": 1.0,
     "metric": "TVD of hour-of-day arrival distribution"
    },
    {
     "id": "H-DP",
     "table": "ed_visits",
     "description": "DP query workload (metadata/dp_query_workload_health.json): mean relative error",
     "required": true,
     "score": 1.0,
     "metric": "mean relative error over workload (unanswered = 1)"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.3554,
    "utility": 0.8674,
    "composite": 0.4857
   },
   "risk_components": {
    "clinical_notes: direct identifiers retained": 0.0,
    "clinical_notes: records with k<5": 0.5226,
    "clinical_notes: free-text identifier leakage": 0.8822,
    "ed_visits: direct identifiers retained": 0.0,
    "ed_visits: records with k<5": 1.0,
    "ed_visits: linkage re-identification": 0.095,
    "ed_visits: free-text identifier leakage": 0.0,
    "lab_results: direct identifiers retained": 0.0,
    "lab_results: records with k<5": 0.0237,
    "published_weekly_stats: direct identifiers retained": 0.0,
    "published_weekly_stats: records with k<5": 0.6573
   },
   "utility": [
    {
     "id": "H-U1",
     "table": "ed_visits",
     "description": "Weekly influenza-like-illness visits by 10-year age band",
     "required": true,
     "score": 0.8747,
     "metric": "MAPE of weekly ILI counts by age band (cells >=3)"
    },
    {
     "id": "H-U2",
     "table": "ed_visits",
     "description": "Median length of stay by triage level",
     "required": true,
     "score": 1.0,
     "metric": "mean relative error of median LOS by triage"
    },
    {
     "id": "H-U3",
     "table": "ed_visits",
     "description": "Admission prediction: train on protected, test on original/holdout (AUC ratio)",
     "required": true,
     "score": 1.0,
     "metric": "(AUC_protected-0.5)/(AUC_original-0.5), train on X, test on original"
    },
    {
     "id": "H-U4",
     "table": "ed_visits",
     "description": "Diagnosis-group mix in the eight largest municipalities",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean TVD/0.15 of diagnosis-group mix in top-8 municipalities"
    },
    {
     "id": "H-U5",
     "table": "ed_visits",
     "description": "Distributions of systolic BP, heart rate, temperature and SpO2",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean Wasserstein distance / IQR over 4 vitals"
    },
    {
     "id": "H-U6",
     "table": "ed_visits",
     "description": "30-day revisit rate by age band (needs readmit_30d or a consistent patient pseudonym)",
     "required": true,
     "score": 0.9642,
     "metric": "mean |revisit rate diff| by age band / overall rate"
    },
    {
     "id": "H-U7",
     "table": "lab_results",
     "description": "CRP vs temperature relationship and CRP by diagnosis group (needs visit join)",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "H-U8",
     "table": "ed_visits",
     "description": "Hour-of-day arrival curve",
     "required": true,
     "score": 1.0,
     "metric": "TVD of hour-of-day arrival distribution"
    },
    {
     "id": "H-DP",
     "table": "ed_visits",
     "description": "DP query workload (metadata/dp_query_workload_health.json): mean relative error",
     "required": true,
     "score": 0.9678,
     "metric": "mean relative error over workload (unanswered = 1)"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.5188,
    "utility": 0.4437,
    "composite": 0.4817
   },
   "risk_components": {
    "clinical_notes: direct identifiers retained": 0.0,
    "clinical_notes: records with k<5": 0.0,
    "clinical_notes: free-text identifier leakage": 0.8822,
    "ed_visits: direct identifiers retained": 0.0,
    "ed_visits: records with k<5": 0.0001,
    "ed_visits: linkage re-identification": 0.0,
    "ed_visits: free-text identifier leakage": 0.0,
    "lab_results: direct identifiers retained": 0.0,
    "lab_results: records with k<5": 0.0,
    "published_weekly_stats: direct identifiers retained": 0.0,
    "published_weekly_stats: records with k<5": 0.0
   },
   "utility": [
    {
     "id": "H-U1",
     "table": "ed_visits",
     "description": "Weekly influenza-like-illness visits by 10-year age band",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "H-U2",
     "table": "ed_visits",
     "description": "Median length of stay by triage level",
     "required": true,
     "score": 1.0,
     "metric": "mean relative error of median LOS by triage"
    },
    {
     "id": "H-U3",
     "table": "ed_visits",
     "description": "Admission prediction: train on protected, test on original/holdout (AUC ratio)",
     "required": true,
     "score": 1.0,
     "metric": "(AUC_protected-0.5)/(AUC_original-0.5), train on X, test on original"
    },
    {
     "id": "H-U4",
     "table": "ed_visits",
     "description": "Diagnosis-group mix in the eight largest municipalities",
     "required": true,
     "score": 0.9931,
     "metric": "1 - mean TVD/0.15 of diagnosis-group mix in top-8 municipalities"
    },
    {
     "id": "H-U5",
     "table": "ed_visits",
     "description": "Distributions of systolic BP, heart rate, temperature and SpO2",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean Wasserstein distance / IQR over 4 vitals"
    },
    {
     "id": "H-U6",
     "table": "ed_visits",
     "description": "30-day revisit rate by age band (needs readmit_30d or a consistent patient pseudonym)",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "H-U7",
     "table": "lab_results",
     "description": "CRP vs temperature relationship and CRP by diagnosis group (needs visit join)",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "H-U8",
     "table": "ed_visits",
     "description": "Hour-of-day arrival curve",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "H-DP",
     "table": "ed_visits",
     "description": "DP query workload (metadata/dp_query_workload_health.json): mean relative error",
     "required": true,
     "score": 0.0,
     "metric": "mean relative error over workload (unanswered = 1)"
    }
   ]
  },
  "Quickstart": {
   "summary": {
    "privacy": 0.3731,
    "utility": 0.7928,
    "composite": 0.4913
   },
   "risk_components": {
    "ed_visits: direct identifiers retained": 0.0,
    "ed_visits: records with k<5": 0.9921,
    "ed_visits: linkage re-identification": 0.055,
    "ed_visits: free-text identifier leakage": 0.0
   },
   "utility": [
    {
     "id": "H-U2",
     "table": "ed_visits",
     "description": "Median length of stay by triage level",
     "required": true,
     "score": 1.0,
     "metric": "mean relative error of median LOS by triage"
    },
    {
     "id": "H-U4",
     "table": "ed_visits",
     "description": "Diagnosis-group mix in the eight largest municipalities",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean TVD/0.15 of diagnosis-group mix in top-8 municipalities"
    },
    {
     "id": "H-U6",
     "table": "ed_visits",
     "description": "30-day revisit rate by age band (needs readmit_30d or a consistent patient pseudonym)",
     "required": true,
     "score": 0.9642,
     "metric": "mean |revisit rate diff| by age band / overall rate"
    },
    {
     "id": "H-U7",
     "table": "lab_results",
     "description": "CRP vs temperature relationship and CRP by diagnosis group (needs visit join)",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "H-U8",
     "table": "ed_visits",
     "description": "Hour-of-day arrival curve",
     "required": true,
     "score": 1.0,
     "metric": "TVD of hour-of-day arrival distribution"
    }
   ]
  }
 },
 "mobility": {
  "B0": {
   "summary": {
    "privacy": 0.3359,
    "utility": 1.0,
    "composite": 0.4812
   },
   "risk_components": {
    "bike_stations: direct identifiers retained": 0.0,
    "bike_trips: direct identifiers retained": 0.0,
    "bike_trips: records with k<5": 1.0,
    "bike_trips: trajectory unicity (user_account)": 0.0,
    "bike_trips: linkage re-identification": 0.0089,
    "cards: direct identifiers retained": 0.0,
    "cards: records with k<5": 0.9587,
    "cards: linkage re-identification": 0.0,
    "stops: direct identifiers retained": 0.0,
    "taps: direct identifiers retained": 0.0,
    "taps: records with k<5": 1.0,
    "taps: trajectory unicity (card_id)": 0.97
   },
   "utility": [
    {
     "id": "MOB-U1",
     "table": "taps",
     "description": "Weekday OD matrix area x area x hour band (trip chaining)",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over OD cells with >=20 journeys"
    },
    {
     "id": "MOB-U2",
     "table": "taps",
     "description": "Weekday boardings by line x hour",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over line x hour cells with >=50 boardings"
    },
    {
     "id": "MOB-U3",
     "table": "taps",
     "description": "Daily boardings time series (school break dip, weekends)",
     "required": true,
     "score": 1.0,
     "metric": "(1 - MAPE/0.3) x Pearson r of daily boardings"
    },
    {
     "id": "MOB-U4",
     "table": "bike_trips",
     "description": "Bike trip duration distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of duration histogram (2-min bins)"
    },
    {
     "id": "MOB-U5",
     "table": "taps",
     "description": "Home-area -> work-area commuting flows (card-days)",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over home-area x work-area card-day flows (>=10)"
    },
    {
     "id": "MOB-U6",
     "table": "bike_trips",
     "description": "Bike zone demand: starts by zone x hour band",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over zone x hour-band starts (>=20)"
    },
    {
     "id": "MOB-U7",
     "table": "bike_trips",
     "description": "Bike ridden-distance distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of ridden distance histogram (500 m bins)"
    },
    {
     "id": "MOB-U8",
     "table": "cards",
     "description": "Card-type mix (fare policy)",
     "required": true,
     "score": 1.0,
     "metric": "1 - 4*TVD of card-type mix"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.3605,
    "utility": 0.9797,
    "composite": 0.5058
   },
   "risk_components": {
    "bike_stations: direct identifiers retained": 0.0,
    "bike_trips: direct identifiers retained": 0.0,
    "bike_trips: records with k<5": 1.0,
    "bike_trips: trajectory unicity (user_account)": 0.0,
    "bike_trips: linkage re-identification": 0.0,
    "cards: direct identifiers retained": 0.0,
    "cards: records with k<5": 0.9587,
    "cards: linkage re-identification": 0.0,
    "stops: direct identifiers retained": 0.0,
    "taps: direct identifiers retained": 0.0,
    "taps: records with k<5": 0.4153,
    "taps: trajectory unicity (card_id)": 0.974
   },
   "utility": [
    {
     "id": "MOB-U1",
     "table": "taps",
     "description": "Weekday OD matrix area x area x hour band (trip chaining)",
     "required": true,
     "score": 0.8458,
     "metric": "1 - MAPE/0.5 over OD cells with >=20 journeys"
    },
    {
     "id": "MOB-U2",
     "table": "taps",
     "description": "Weekday boardings by line x hour",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over line x hour cells with >=50 boardings"
    },
    {
     "id": "MOB-U3",
     "table": "taps",
     "description": "Daily boardings time series (school break dip, weekends)",
     "required": true,
     "score": 1.0,
     "metric": "(1 - MAPE/0.3) x Pearson r of daily boardings"
    },
    {
     "id": "MOB-U4",
     "table": "bike_trips",
     "description": "Bike trip duration distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of duration histogram (2-min bins)"
    },
    {
     "id": "MOB-U5",
     "table": "taps",
     "description": "Home-area -> work-area commuting flows (card-days)",
     "required": true,
     "score": 0.9917,
     "metric": "1 - MAPE/0.5 over home-area x work-area card-day flows (>=10)"
    },
    {
     "id": "MOB-U6",
     "table": "bike_trips",
     "description": "Bike zone demand: starts by zone x hour band",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over zone x hour-band starts (>=20)"
    },
    {
     "id": "MOB-U7",
     "table": "bike_trips",
     "description": "Bike ridden-distance distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of ridden distance histogram (500 m bins)"
    },
    {
     "id": "MOB-U8",
     "table": "cards",
     "description": "Card-type mix (fare policy)",
     "required": true,
     "score": 1.0,
     "metric": "1 - 4*TVD of card-type mix"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.5103,
    "utility": 0.5241,
    "composite": 0.5165
   },
   "risk_components": {
    "bike_stations: direct identifiers retained": 0.0,
    "bike_trips: direct identifiers retained": 0.0,
    "bike_trips: records with k<5": 0.0001,
    "bike_trips: trajectory unicity (user_account)": 0.0,
    "bike_trips: linkage re-identification": 0.0,
    "cards: direct identifiers retained": 0.0,
    "cards: records with k<5": 0.0,
    "cards: linkage re-identification": 0.0,
    "stops: direct identifiers retained": 0.0,
    "taps: direct identifiers retained": 0.0,
    "taps: records with k<5": 0.0,
    "taps: trajectory unicity (card_id)": 0.904
   },
   "utility": [
    {
     "id": "MOB-U1",
     "table": "taps",
     "description": "Weekday OD matrix area x area x hour band (trip chaining)",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 over OD cells with >=20 journeys"
    },
    {
     "id": "MOB-U2",
     "table": "taps",
     "description": "Weekday boardings by line x hour",
     "required": true,
     "score": 0.4038,
     "metric": "1 - MAPE/0.5 over line x hour cells with >=50 boardings"
    },
    {
     "id": "MOB-U3",
     "table": "taps",
     "description": "Daily boardings time series (school break dip, weekends)",
     "required": true,
     "score": 0.7887,
     "metric": "(1 - MAPE/0.3) x Pearson r of daily boardings"
    },
    {
     "id": "MOB-U4",
     "table": "bike_trips",
     "description": "Bike trip duration distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of duration histogram (2-min bins)"
    },
    {
     "id": "MOB-U5",
     "table": "taps",
     "description": "Home-area -> work-area commuting flows (card-days)",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 over home-area x work-area card-day flows (>=10)"
    },
    {
     "id": "MOB-U6",
     "table": "bike_trips",
     "description": "Bike zone demand: starts by zone x hour band",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 over zone x hour-band starts (>=20)"
    },
    {
     "id": "MOB-U7",
     "table": "bike_trips",
     "description": "Bike ridden-distance distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of ridden distance histogram (500 m bins)"
    },
    {
     "id": "MOB-U8",
     "table": "cards",
     "description": "Card-type mix (fare policy)",
     "required": true,
     "score": 1.0,
     "metric": "1 - 4*TVD of card-type mix"
    }
   ]
  }
 },
 "public_admin": {
  "B0": {
   "summary": {
    "privacy": 0.25,
    "utility": 1.0,
    "composite": 0.3793
   },
   "risk_components": {
    "building_permits: direct identifiers retained": 0.0,
    "building_permits: records with k<5": 1.0,
    "service_requests: direct identifiers retained": 0.0,
    "service_requests: records with k<5": 1.0,
    "service_requests: linkage re-identification": 0.0,
    "service_requests: free-text identifier leakage": 1.0
   },
   "utility": [
    {
     "id": "PUB-U1",
     "table": "service_requests",
     "description": "Request counts by area (3-digit postcode) x category x month",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE over (3-digit postcode, category, month) cells with n>=5 / 0.5"
    },
    {
     "id": "PUB-U2",
     "table": "service_requests",
     "description": "Median resolution time by category",
     "required": true,
     "score": 1.0,
     "metric": "1 - mean relative error of median resolution hours per category / 0.5"
    },
    {
     "id": "PUB-U3",
     "table": "service_requests",
     "description": "Hotspot map: top-50 1 km grid cells",
     "required": true,
     "score": 1.0,
     "metric": "Jaccard overlap of top-50 1 km grid cells by request count"
    },
    {
     "id": "PUB-U4",
     "table": "service_requests",
     "description": "Category classifier trained on protected description text",
     "required": true,
     "score": 1.0,
     "metric": "accuracy retention: classifier trained on protected text, tested on original hold-out"
    },
    {
     "id": "PUB-U5",
     "table": "service_requests",
     "description": "Share of requests from repeat reporters (>=5 requests per account)",
     "required": true,
     "score": 1.0,
     "metric": "1 - |error| / 0.15 in share of account requests from accounts with >=5 requests"
    },
    {
     "id": "PUB-U6",
     "table": "building_permits",
     "description": "Permit counts by municipality x project type x quarter",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE over (municipality, project type, quarter) cells with n>=5 / 0.5"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.2717,
    "utility": 0.9299,
    "composite": 0.4006
   },
   "risk_components": {
    "building_permits: direct identifiers retained": 0.0,
    "building_permits: records with k<5": 1.0,
    "service_requests: direct identifiers retained": 0.0,
    "service_requests: records with k<5": 1.0,
    "service_requests: linkage re-identification": 0.0,
    "service_requests: free-text identifier leakage": 0.7395
   },
   "utility": [
    {
     "id": "PUB-U1",
     "table": "service_requests",
     "description": "Request counts by area (3-digit postcode) x category x month",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE over (3-digit postcode, category, month) cells with n>=5 / 0.5"
    },
    {
     "id": "PUB-U2",
     "table": "service_requests",
     "description": "Median resolution time by category",
     "required": true,
     "score": 0.9944,
     "metric": "1 - mean relative error of median resolution hours per category / 0.5"
    },
    {
     "id": "PUB-U3",
     "table": "service_requests",
     "description": "Hotspot map: top-50 1 km grid cells",
     "required": true,
     "score": 0.6393,
     "metric": "Jaccard overlap of top-50 1 km grid cells by request count"
    },
    {
     "id": "PUB-U4",
     "table": "service_requests",
     "description": "Category classifier trained on protected description text",
     "required": true,
     "score": 0.9454,
     "metric": "accuracy retention: classifier trained on protected text, tested on original hold-out"
    },
    {
     "id": "PUB-U5",
     "table": "service_requests",
     "description": "Share of requests from repeat reporters (>=5 requests per account)",
     "required": true,
     "score": 1.0,
     "metric": "1 - |error| / 0.15 in share of account requests from accounts with >=5 requests"
    },
    {
     "id": "PUB-U6",
     "table": "building_permits",
     "description": "Permit counts by municipality x project type x quarter",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE over (municipality, project type, quarter) cells with n>=5 / 0.5"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.5686,
    "utility": 0.4353,
    "composite": 0.4992
   },
   "risk_components": {
    "building_permits: direct identifiers retained": 0.0,
    "building_permits: records with k<5": 0.0,
    "service_requests: direct identifiers retained": 0.0,
    "service_requests: records with k<5": 0.0,
    "service_requests: linkage re-identification": 0.0,
    "service_requests: free-text identifier leakage": 0.7395
   },
   "utility": [
    {
     "id": "PUB-U1",
     "table": "service_requests",
     "description": "Request counts by area (3-digit postcode) x category x month",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE over (3-digit postcode, category, month) cells with n>=5 / 0.5"
    },
    {
     "id": "PUB-U2",
     "table": "service_requests",
     "description": "Median resolution time by category",
     "required": true,
     "score": 0.0,
     "metric": "1 - mean relative error of median resolution hours per category / 0.5"
    },
    {
     "id": "PUB-U3",
     "table": "service_requests",
     "description": "Hotspot map: top-50 1 km grid cells",
     "required": true,
     "score": 0.6667,
     "metric": "Jaccard overlap of top-50 1 km grid cells by request count"
    },
    {
     "id": "PUB-U4",
     "table": "service_requests",
     "description": "Category classifier trained on protected description text",
     "required": true,
     "score": 0.9454,
     "metric": "accuracy retention: classifier trained on protected text, tested on original hold-out"
    },
    {
     "id": "PUB-U5",
     "table": "service_requests",
     "description": "Share of requests from repeat reporters (>=5 requests per account)",
     "required": true,
     "score": 1.0,
     "metric": "1 - |error| / 0.15 in share of account requests from accounts with >=5 requests"
    },
    {
     "id": "PUB-U6",
     "table": "building_permits",
     "description": "Permit counts by municipality x project type x quarter",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE over (municipality, project type, quarter) cells with n>=5 / 0.5"
    }
   ]
  }
 },
 "smart_city": {
  "B0": {
   "summary": {
    "privacy": 0.3387,
    "utility": 0.8333,
    "composite": 0.4638
   },
   "risk_components": {
    "anpr_parking: direct identifiers retained": 0.0,
    "anpr_parking: records with k<5": 1.0,
    "anpr_parking: trajectory unicity (plate)": 0.0,
    "anpr_parking: linkage re-identification": 0.0,
    "footfall_15min: direct identifiers retained": 0.0,
    "sensors: direct identifiers retained": 0.0,
    "wifi_probes: direct identifiers retained": 0.0,
    "wifi_probes: records with k<5": 1.0,
    "wifi_probes: trajectory unicity (mac)": 0.904
   },
   "utility": [
    {
     "id": "CITY-U1",
     "table": "footfall_15min",
     "description": "Footfall by zone x hour x weekday/weekend",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over zone x hour x day-type footfall (cells >=30)"
    },
    {
     "id": "CITY-U2",
     "table": "wifi_probes",
     "description": "Dwell-time distribution per device-day",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of per-device-day dwell span histogram"
    },
    {
     "id": "CITY-U3",
     "table": "anpr_parking",
     "description": "Mean car-park occupancy by hour of day",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 of mean occupancy by car park x hour"
    },
    {
     "id": "CITY-U4",
     "table": "anpr_parking",
     "description": "Share of repeat visitors (plates seen on >=2 days)",
     "required": true,
     "score": null,
     "metric": "not answerable"
    },
    {
     "id": "CITY-U5",
     "table": "footfall_15min",
     "description": "Black Friday uplift vs previous Friday",
     "required": true,
     "score": 1.0,
     "metric": "1 - relerr/0.3 of Black Friday / previous Friday footfall ratio"
    },
    {
     "id": "CITY-U6",
     "table": "anpr_parking",
     "description": "Parking duration distribution",
     "required": true,
     "score": 1.0,
     "metric": "1 - 2*TVD of parking duration histogram"
    }
   ]
  },
  "B2": {
   "summary": {
    "privacy": 0.4507,
    "utility": 0.7415,
    "composite": 0.5485
   },
   "risk_components": {
    "anpr_parking: direct identifiers retained": 0.0,
    "anpr_parking: records with k<5": 0.1909,
    "anpr_parking: trajectory unicity (plate)": 0.585,
    "anpr_parking: linkage re-identification": 0.0,
    "footfall_15min: direct identifiers retained": 0.0,
    "sensors: direct identifiers retained": 0.0,
    "wifi_probes: direct identifiers retained": 0.0,
    "wifi_probes: records with k<5": 0.0807,
    "wifi_probes: trajectory unicity (mac)": 0.903
   },
   "utility": [
    {
     "id": "CITY-U1",
     "table": "footfall_15min",
     "description": "Footfall by zone x hour x weekday/weekend",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over zone x hour x day-type footfall (cells >=30)"
    },
    {
     "id": "CITY-U2",
     "table": "wifi_probes",
     "description": "Dwell-time distribution per device-day",
     "required": true,
     "score": 0.0,
     "metric": "1 - 2*TVD of per-device-day dwell span histogram"
    },
    {
     "id": "CITY-U3",
     "table": "anpr_parking",
     "description": "Mean car-park occupancy by hour of day",
     "required": true,
     "score": 0.7456,
     "metric": "1 - MAPE/0.5 of mean occupancy by car park x hour"
    },
    {
     "id": "CITY-U4",
     "table": "anpr_parking",
     "description": "Share of repeat visitors (plates seen on >=2 days)",
     "required": true,
     "score": 1.0,
     "metric": "1 - relerr/0.3 of share of plates seen on >=2 days"
    },
    {
     "id": "CITY-U5",
     "table": "footfall_15min",
     "description": "Black Friday uplift vs previous Friday",
     "required": true,
     "score": 1.0,
     "metric": "1 - relerr/0.3 of Black Friday / previous Friday footfall ratio"
    },
    {
     "id": "CITY-U6",
     "table": "anpr_parking",
     "description": "Parking duration distribution",
     "required": true,
     "score": 0.7035,
     "metric": "1 - 2*TVD of parking duration histogram"
    }
   ]
  },
  "B2-k": {
   "summary": {
    "privacy": 0.4681,
    "utility": 0.5885,
    "composite": 0.5161
   },
   "risk_components": {
    "anpr_parking: direct identifiers retained": 0.0,
    "anpr_parking: records with k<5": 0.0,
    "anpr_parking: trajectory unicity (plate)": 0.585,
    "anpr_parking: linkage re-identification": 0.0,
    "footfall_15min: direct identifiers retained": 0.0,
    "sensors: direct identifiers retained": 0.0,
    "wifi_probes: direct identifiers retained": 0.0,
    "wifi_probes: records with k<5": 0.0,
    "wifi_probes: trajectory unicity (mac)": 0.899
   },
   "utility": [
    {
     "id": "CITY-U1",
     "table": "footfall_15min",
     "description": "Footfall by zone x hour x weekday/weekend",
     "required": true,
     "score": 1.0,
     "metric": "1 - MAPE/0.5 over zone x hour x day-type footfall (cells >=30)"
    },
    {
     "id": "CITY-U2",
     "table": "wifi_probes",
     "description": "Dwell-time distribution per device-day",
     "required": true,
     "score": 0.0,
     "metric": "1 - 2*TVD of per-device-day dwell span histogram"
    },
    {
     "id": "CITY-U3",
     "table": "anpr_parking",
     "description": "Mean car-park occupancy by hour of day",
     "required": true,
     "score": 0.0,
     "metric": "1 - MAPE/0.5 of mean occupancy by car park x hour"
    },
    {
     "id": "CITY-U4",
     "table": "anpr_parking",
     "description": "Share of repeat visitors (plates seen on >=2 days)",
     "required": true,
     "score": 0.9377,
     "metric": "1 - relerr/0.3 of share of plates seen on >=2 days"
    },
    {
     "id": "CITY-U5",
     "table": "footfall_15min",
     "description": "Black Friday uplift vs previous Friday",
     "required": true,
     "score": 1.0,
     "metric": "1 - relerr/0.3 of Black Friday / previous Friday footfall ratio"
    },
    {
     "id": "CITY-U6",
     "table": "anpr_parking",
     "description": "Parking duration distribution",
     "required": true,
     "score": 0.5935,
     "metric": "1 - 2*TVD of parking duration histogram"
    }
   ]
  }
 }
}
