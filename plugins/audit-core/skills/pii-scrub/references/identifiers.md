# Identifiers and de-identification reference

## HIPAA Safe Harbor: the 18 identifier types

Under HIPAA's Safe Harbor method, data is considered de-identified once these are removed for the individual and their relatives, employers, or household members, and there is no actual knowledge that the rest could identify someone.

1. Names
2. Geographic subdivisions smaller than a state (street, city, county, precinct, ZIP). The first 3 ZIP digits may stay if that area has more than 20,000 people.
3. All date elements except year that relate to an individual (birth, admission, discharge, death), and ages over 89
4. Phone numbers
5. Fax numbers
6. Email addresses
7. Social Security numbers
8. Medical record numbers
9. Health plan beneficiary numbers
10. Account numbers
11. Certificate or license numbers
12. Vehicle identifiers and serial numbers, including license plates
13. Device identifiers and serial numbers
14. Web URLs
15. IP addresses
16. Biometric identifiers (fingerprints, voiceprints)
17. Full-face photographs and comparable images
18. Any other unique identifying number, characteristic, or code

The alternative is Expert Determination, where a qualified expert certifies the re-identification risk is very small.

## Glossary

| Term | Meaning | Still personal data? |
| --- | --- | --- |
| Data minimization | Collect and keep only what the purpose needs | Nothing to protect if never collected |
| Anonymization | Irreversibly remove identity | No |
| De-identification | Umbrella term; under HIPAA, meeting Safe Harbor or Expert Determination | No, if the standard is met |
| Pseudonymization | Replace identifiers with tokens; a key could reverse it | Yes, under GDPR, while a key exists |
| Masking | Replace a value with a placeholder | Depends on what remains |
| Generalization | Coarsen values (year instead of date) | Depends on what remains |
| Data scrubbing | General cleanup, may include PII removal | Depends on what remains |

## Which law usually applies (not legal advice)

- **HIPAA:** health information held by covered entities (providers, plans, clearinghouses) and their business associates.
- **FERPA:** education records held by schools receiving federal funding.
- **GDPR:** personal data of people in the EU or EEA; rarely relevant to US-only programs.
- **Institution policy:** employers and hospitals often set stricter rules than the law. When in doubt, the organization's privacy office decides.

## Small group risk

Removing direct identifiers is not enough when groups are small. A rule of thumb used in many reporting settings is to suppress or combine any cell describing fewer than 5 to 11 people, depending on the organization. Watch combinations too: role plus year plus location can point to one person even when each field alone doesn't.
