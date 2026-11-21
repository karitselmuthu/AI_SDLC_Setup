# Acme Retail: enterprise standards extract (sample, made-up data)

## Approved platforms
- Approved public cloud: AWS (regions eu-west-1 and eu-central-1 only) and Azure (West Europe, North Europe).
- SaaS products must be on the Approved Vendor List. Adding a vendor needs a security review (6 to 8 weeks).
- Approved identity platform: Okta for staff. Customer identity is not covered by the Okta licence (staff identities only, 5,000 seats).

## Security policy
- SaaS vendors must hold ISO 27001 and SOC 2 Type II, and sign Acme's data processing agreement (DPA).
- Customer personal data is classified Confidential: encryption at rest (AES-256) and in transit (TLS 1.2 or higher).
- Audit logs must be retained 12 months and be exportable to Acme's SIEM.
- Admin access to production systems requires MFA and a named individual account.

## Data residency and regulatory
- Customer data must be stored and processed in the EU. Sub-processors must be listed and approved by Acme.
- Acme operates in the EU and the UK. Applicable privacy law has not been listed in this extract.

## Accessibility
- Customer-facing web properties must meet WCAG 2.1 AA.

## Existing contracts and services
- Salesforce enterprise agreement runs to March 2027 and includes Service Cloud licences (unused).
- HelpDeskOne contract renews in January and has a 90-day notice period.
- TicketWorks is out of vendor support and has no active contract.
- Okta contract covers staff only.
