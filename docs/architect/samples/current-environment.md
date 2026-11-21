# Acme Retail: support tooling environment (sample, made-up data)

## Systems inventory
| System | Purpose | Owner | Tech | Hosting |
|---|---|---|---|---|
| HelpDeskOne | Email tickets, EMEA team | Support EMEA | Vendor SaaS, v7 | Vendor cloud, region not recorded |
| TicketWorks | Phone tickets, US team | Support US | On-prem, Windows Server 2012, SQL Server 2014 | Chicago data centre |
| FormTracker | Web-form tickets | Web team | Custom PHP 5.6 app, MySQL 5.5 | AWS us-east-1 |
| Okta | Staff SSO | IT | SaaS | Vendor cloud |
| Salesforce | Customer records | Sales ops | SaaS | Vendor cloud |

## Architecture notes (from the architecture team's diagram description)
- HelpDeskOne, TicketWorks and FormTracker do not talk to each other. Agents copy customer details by hand.
- Salesforce customer IDs are typed into TicketWorks manually. There is a nightly CSV export from FormTracker to Salesforce.
- Staff sign in through Okta for HelpDeskOne and Salesforce only. TicketWorks uses local Windows accounts.
- A fourth tool, "ChatBridge", appears on the diagram connecting to HelpDeskOne. It is not in the inventory.

## Standards and constraints
- IT standard: all new systems must authenticate through Okta (SAML 2.0 or OIDC).
- Security policy: no new on-prem hosting. Customer data must be encrypted at rest and in transit.
- Change freeze: 1 November to 5 January (holiday trading).
- Procurement: new vendors need a security review, typically 6 to 8 weeks.

## Known pain points
- Support staff say they retype customer details between tools several times a day.
- Reporting on response times requires merging three spreadsheets by hand.
- TicketWorks server is out of vendor support.
