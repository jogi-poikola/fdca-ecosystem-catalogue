# Prompt: restructure the FDCA categorisation

Pass this to whatever maintains the source categorisation file. It describes the
target taxonomy in full, so it can be applied without reference to the catalogue app.

---

Restructure the FDCA member categorisation from nine top-level categories into
**five families**. Colour is carried by the family; the specific is carried by the
subcategory label. Every member keeps its identity — only its `category` /
`subcategory` assignment changes.

## Target families

**1. Data Center Operators** — unchanged. No subcategories.

**2. Technology Vendors** — keep its existing subcategories. Rename its catch-all
group from "Other" to **"Other technology"**.

**3. Construction** — keep its existing subcategories. Rename its catch-all group
from "Other" to **"Other construction"**.

**4. Services** — keep its existing subcategories, and add two that were previously
top-level categories in their own right:
- **Renewable Energy** (was the `renewable_energy` category)
- **Connectivity** (was the `connectivity` category)

Rename its catch-all group from "Other" to **"Other services"**.

**5. Planning** — a NEW family. It has no members of its own; it exists to hold
three former top-level categories as subcategories:
- **Design Engineering** (was `design_engineering`)
- **Site Developers** (was `site_developers`)
- **Municipalities** (was `municipalities`)

Its catch-all group, should one arise, is **"Other planning"**.

## Rules

- A member whose category becomes a subcategory keeps its old category slug as its
  new subcategory slug. E.g. a member in `connectivity` becomes
  `category: services, subcategory: connectivity`.
- A member already carrying a subcategory inside a surviving family
  (Technology Vendors, Construction, Services) keeps that subcategory unchanged.
- **A family with no subcategories is displayed by its own name** — do not
  invent a subcategory to hold its members. Only Data Center Operators is in
  this position.
- Catch-all group labels are explicit, never the bare word "Other":
  "Other technology", "Other construction", "Other services", "Other planning".
- Family display order: Data Center Operators, Technology Vendors, Construction,
  Services, Planning.

## Colour

One hue per family, ≥30° apart in OKLCH so no two families read as the same colour.
Subcategories are NOT separate hues — they share the family hue and are distinguished
by their label and border. Suggested family hues:

| Family | OKLCH hue | Note |
| --- | --- | --- |
| Data Center Operators | 170 | teal |
| Services | 100 | olive/green |
| Planning | 232 | blue |
| Technology Vendors | 300 | violet |
| Construction | 15 | red-orange |

FDCA blue `#020381` is reserved for the masthead and must not be used for a family.

## Finnish labels

Provide `fi` for the new family: **Planning → Suunnittelu**. Existing families keep
their current Finnish labels; former categories keep theirs as subcategory labels.
