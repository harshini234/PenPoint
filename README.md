# PenPoint: BRD Decision Aid

AISFS × Merck Animal Health Hackathon 2026, Problem 1.
Team: Aditi Walvekar, Shriya Shah, Sree Harshini Satheeskumar.

**Live dashboard:** https://penpoint-brd.streamlit.app/ (free, no paid access)
**Repository:** https://github.com/harshini234/PenPoint

PenPoint is a decision aid for bovine respiratory disease (BRD) in the first 45 days after feedlot arrival. It answers
which arriving lots are high risk, why, and whether metaphylaxis is worth its cost for each one at 2026 prices.
Risk comes from a decision tree built the way Rojas et al. (2022) built theirs, adjusted for each lot's own
preconditioning, vaccination, haul time, purchase channel and weight. Costs use the paper's net health cost benefit
equations (Eqs 1 to 5). The plan never expects more BRD deaths than the yard's current approach (with a 5% safety margin).

All data are synthetic and fictional. Medication recommendations are decision support only and remain subject to
veterinary review.

## Use the live dashboard
1. Open the link and click **Open PenPoint**.
2. Sign in: any email and password work (or leave them blank). Click **Sign in**.
3. If no lots appear, go to **Lot management → Add or import data** and upload the three files in `demo_data/`:
   `cattle.csv` (required), `health_records.csv` and `sensehub_alerts.csv`. Click **Import**.
4. Explore **Herd status → Risk overview**, then **Management options → Treatment options**.

The free host may sleep or reset after inactivity. If the data are gone, upload the demo files again.

## Run locally
    python3 -m venv .venv
    source .venv/bin/activate          # Windows: .venv\Scripts\activate
    python -m pip install -r requirements.txt
    python -m streamlit run app/streamlit_app.py
    python scripts/import_demo.py      # optional: loads the demo files without the browser

Open http://localhost:8501. Requires Python 3.10 or newer. Data are saved to `data/penpoint.db`; delete it to start over.

## Demo data (`demo_data/`)
| File | Contents |
|---|---|
| `cattle.csv` | 1,972 cattle in 18 lots, one row per animal with its lot's details |
| `health_records.csv` | 132 records: first BRD treatments, retreatments and deaths, with drug, withdrawal days and temperature |
| `sensehub_alerts.csv` | One day's SenseHub alert report (16 alerts) |

Column definitions are in `docs/data_dictionary.md`. Records run to Nov 14, 2026, so importing sets PenPoint's date to
that day. Regenerate the files with `python scripts/make_demo_data.py`.

## What's in the app
| Section | Pages |
|---|---|
| Lot management | **Lots and cattle** (every lot and animal, treatment records with drug and withdrawal date, editable) · **Add or import data** · **Constraints and assumptions** (2026 costs, risk-factor effects, treatment protocol, current approach, safety margin) |
| Herd status | **Risk overview**: lots ranked by risk score with the reasons for each rating, and the cattle that need attention today |
| Management options | **Treatment options** (recommended plan and four approaches compared) · **Lot-level cost analysis** · **Scenario analysis** · **Decision summary** (one page for vet sign-off) · **Daily action list** · **Treatment response** |
| About the model | **Methods and equations** · **Model validation** · **Parameter sources** · **Brief requirements** |

## Repository map
| Path | What it is |
|---|---|
| `app/streamlit_app.py` | Dashboard entry point |
| `app/penpoint/model.py` | Decision tree, risk adjustment, cost equations and plan |
| `app/penpoint/bulk.py`, `app/penpoint/data.py`, `app/penpoint/db.py` | Data import, lot calculations and storage |
| `src/brd/generator.py`, `src/brd/params.py` | Simulation that produced the training history |
| `data/demo/lots_history.csv` | 1,500 simulated past lots used to train the risk model |
| `params/parameters.yaml` | All 90 parameters with value, range, source and evidence label |
| `demo_data/`, `scripts/make_demo_data.py`, `scripts/import_demo.py` | Demo files, their generator and command-line import |
| `docs/demo_case.md` | Demonstration case: arrival decision for 7 lots |
| `docs/data_dictionary.md` | Column definitions |
| `docs/generator_validation.md` | Check of the simulation against published figures |

## Limitations
- All data are simulated and calibrated to published figures; accuracy on real cattle is unknown.
- 43 of 90 parameters are labelled assumptions, and four of the five risk-factor effects are assumed. All are editable.
- High-risk lots are rare, so the cutoff is low (8.5%) and many lots are rated high risk; the risk score shows how strong each rating is.
- Our corrected reading of Rojas et al.'s Equation 3 is an interpretation, explained in the app.
- Hospital pen space, labour and nutrition are not modelled.
- The drug protocol is an example; the veterinarian and product labels decide drug, dose and withdrawal.
