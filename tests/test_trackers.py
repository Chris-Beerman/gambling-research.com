"""Trials, bills and court trackers: parsing, relevance, derived stages and merging."""
import datetime as dt

from pipeline.common import load_yaml
from pipeline.normalize import Taxonomy
from pipeline.sources import bills, courts, trials
from pipeline.trackers import court_level, stage_from_actions, stage_from_text, update_bills, update_cases, update_trials

TAX = Taxonomy(load_yaml("taxonomy.yml"))
TODAY = dt.date(2026, 10, 17)

CT_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT06000001", "briefTitle": "App-based CBT for gambling disorder", "officialTitle": "A randomised trial of app-based cognitive behavioural therapy for gambling disorder"},
        "statusModule": {
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2026-02-01", "type": "ACTUAL"},
            "primaryCompletionDateStruct": {"date": "2027-06", "type": "ESTIMATED"},
            "studyFirstPostDateStruct": {"date": "2026-01-20", "type": "ACTUAL"},
            "lastUpdatePostDateStruct": {"date": "2026-10-01", "type": "ACTUAL"},
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "University of Calgary", "class": "OTHER"}, "collaborators": [{"name": "Alberta Gambling Research Institute", "class": "OTHER"}]},
        "descriptionModule": {"briefSummary": "This trial tests whether a smartphone app reduces gambling in adults with gambling disorder."},
        "conditionsModule": {"conditions": ["Gambling Disorder"], "keywords": ["sports betting"]},
        "designModule": {"studyType": "INTERVENTIONAL", "phases": ["NA"], "enrollmentInfo": {"count": 300, "type": "ESTIMATED"}},
        "armsInterventionsModule": {"interventions": [{"type": "BEHAVIORAL", "name": "CBT app"}]},
        "contactsLocationsModule": {"locations": [{"facility": "U of C", "city": "Calgary", "country": "Canada"}, {"facility": "X", "city": "Chicago", "country": "United States"}]},
    },
    "hasResults": False,
}

IGT_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT06000002", "briefTitle": "Decision making in Parkinson disease"},
        "statusModule": {"overallStatus": "COMPLETED", "studyFirstPostDateStruct": {"date": "2025-01-01"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Hospital", "class": "OTHER"}},
        "descriptionModule": {"briefSummary": "Participants complete the Iowa Gambling Task before and after treatment."},
        "conditionsModule": {"conditions": ["Parkinson Disease"]},
        "designModule": {"studyType": "OBSERVATIONAL"},
    },
    "hasResults": True,
}

ISRCTN_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<allTrials totalCount="1" xmlns="http://www.67bricks.com/isrctn">
<fullTrial>
<trial lastUpdated="2026-04-10T13:32:29Z" publicIdentifierDateAssigned="2026-04-10T22:17:12Z">
<isrctn dateAssigned="2026-04-10T22:17:12Z">52321342</isrctn>
<trialDescription><title>Opportunistic recruitment for gambling self-help</title><scientificTitle>Gambling help on demand</scientificTitle>
<plainEnglishSummary>This study tests a self-help smartphone app for gambling problems.</plainEnglishSummary></trialDescription>
<externalRefs><doi>10.1186/ISRCTN52321342</doi><clinicalTrialsGovNumber/></externalRefs>
<trialDesign><primaryStudyDesign>Interventional</primaryStudyDesign><overallEndDate>2026-04-30T00:00:00.000Z</overallEndDate></trialDesign>
<participants><recruitmentCountries><country>Canada</country></recruitmentCountries><targetEnrolment>800</targetEnrolment><totalFinalEnrolment>818</totalFinalEnrolment>
<recruitmentStart>2025-02-01T00:00:00.000Z</recruitmentStart><recruitmentEnd>2025-03-30T00:00:00.000Z</recruitmentEnd><recruitmentStatusOverride/></participants>
<conditions><condition><description>High Risk Gambling</description></condition></conditions>
<interventions><intervention><description>Static versus personalised app</description><interventionType>Behavioural</interventionType></intervention></interventions>
<results><publicationStage/><basicReport/></results>
</trial>
<contact><forename>David</forename><surname>Hodgins</surname><contactTypes><contactType>Principal investigator</contactType></contactTypes></contact>
<sponsor><organisation>Alberta Gambling Research Institute</organisation><commercialStatus>Non-commercial</commercialStatus></sponsor>
<funder><name>Alberta Gambling Research Institute, University of Calgary</name></funder>
</fullTrial>
</allTrials>"""

OSF_ITEM = {
    "id": "ab12c",
    "attributes": {"title": "Losing the group chat: a preregistration", "description": "Does sports betting talk in group chats predict escalation?", "date_registered": "2026-09-30T12:00:00.000000Z", "date_modified": "2026-10-01T00:00:00Z", "registration_supplement": "OSF Preregistration", "tags": ["gambling"], "public": True, "withdrawn": False, "embargoed": False},
    "links": {"html": "https://osf.io/ab12c/"},
    "embeds": {"contributors": {"data": [{"embeds": {"users": {"data": {"attributes": {"full_name": "Chris Beerman"}}}}}]}},
}


def test_clinicaltrials_convert_and_relevance():
    r = trials.convert_clinicaltrials(CT_STUDY)
    assert r["id"] == "NCT06000001" and r["status"] == "recruiting" and r["enrollment"] == 300
    assert r["countries"] == ["Canada", "United States"] and r["interventions"] == ["behavioral: CBT app"]
    assert r["completion_date"] == "2027-06-01"
    bad = trials.convert_clinicaltrials(IGT_STUDY)
    out, stats = update_trials([], [r, bad], TAX, TODAY, backfill=True)
    assert stats["dropped_irrelevant"] == 1 and len(out) == 1  # the Iowa Gambling Task study is not a gambling trial
    t = out[0]
    assert t["countries"] == ["CA", "US"] and set(t["regions"]) == {"canada", "us"}
    assert "treatment" in t["topics"] and "sports-betting" in t["topics"]
    assert t["first_seen"] == "2026-01-20"  # backfill uses the first-posted date
    # Nightly rerun with a status change: first_seen stays, status_changed is recorded.
    r2 = dict(r, status="completed")
    out2, stats2 = update_trials(out, [r2], TAX, dt.date(2026, 11, 1), backfill=False)
    assert stats2["updated"] == 1 and out2[0]["first_seen"] == "2026-01-20"
    assert out2[0]["status_changed"] == "2026-11-01" and out2[0]["previous_status"] == "recruiting"
    # A registry fetched in full that no longer returns a record removes it; a failed registry keeps its records.
    out3, stats3 = update_trials(out2, [], TAX, dt.date(2026, 11, 2), backfill=False, refreshed={"clinicaltrials"})
    assert out3 == [] and stats3["removed"] == 1
    out4, _ = update_trials(out2, [], TAX, dt.date(2026, 11, 2), backfill=False, refreshed={"isrctn"})
    assert len(out4) == 1


def test_isrctn_parse():
    recs, total = trials.parse_isrctn(ISRCTN_XML, today=TODAY)
    assert total == 1 and len(recs) == 1
    r = recs[0]
    assert r["id"] == "ISRCTN52321342" and r["url"].endswith("ISRCTN52321342")
    assert r["status"] == "completed" and r["enrollment"] == 818
    assert r["countries"] == ["Canada"] and r["authors"] == ["David Hodgins"]
    assert r["sponsor"] == "Alberta Gambling Research Institute" and r["first_posted"] == "2026-04-10"
    assert r["interventions"] == ["behavioural: Static versus personalised app"]
    # An ISRCTN record that quotes an NCT number already in the index is skipped.
    r["other_ids"] = ["NCT06000001"]
    ct = trials.convert_clinicaltrials(CT_STUDY)
    out, stats = update_trials([], [ct, r], TAX, TODAY, backfill=True)
    assert [t["id"] for t in out] == ["NCT06000001"]


def test_osf_convert():
    r = trials.convert_osf(OSF_ITEM)
    assert r["id"] == "osf:ab12c" and r["kind"] == "registration" and r["status"] == "registered"
    assert r["authors"] == ["Chris Beerman"] and r["registration_type"] == "OSF Preregistration"
    assert r["first_posted"] == "2026-09-30"
    assert trials.convert_osf(dict(OSF_ITEM, attributes=dict(OSF_ITEM["attributes"], withdrawn=True))) is None


OS_BILL = {
    "id": "ocd-bill/1111",
    "identifier": "HB 1234",
    "title": "Sports wagering; self-exclusion program; prediction markets",
    "jurisdiction": {"id": "ocd-jurisdiction/country:us/state:il/government", "name": "Illinois", "classification": "state"},
    "session": "104th", "classification": ["bill"], "subject": ["GAMING"],
    "first_action_date": "2026-01-15", "latest_action_date": "2026-03-02", "latest_action_description": "Third Reading - Passed; 071-040-000", "latest_passage_date": "2026-03-02",
    "openstates_url": "https://openstates.org/il/bills/104th/HB1234/", "updated_at": "2026-03-03T01:00:00+00:00",
    "abstracts": [{"abstract": "Amends the Sports Wagering Act to require event-contract platforms to honour the statewide self-exclusion list."}],
    "sponsorships": [{"name": "Jane Doe", "primary": True}],
    "sources": [{"url": "https://ilga.gov/legislation/x"}],
    "actions": [
        {"date": "2026-01-15", "description": "Filed with the Clerk", "classification": ["filing"], "organization": {"classification": "lower"}},
        {"date": "2026-01-20", "description": "Referred to Rules Committee", "classification": ["referral-committee"], "organization": {"classification": "lower"}},
        {"date": "2026-03-02", "description": "Third Reading - Passed", "classification": ["passage"], "organization": {"classification": "lower"}},
    ],
}


def test_openstates_convert_and_stage():
    r = bills.convert_openstates(OS_BILL)
    assert r["jurisdiction_code"] == "il" and r["identifier"] == "HB 1234" and r["sponsors"] == ["Jane Doe"]
    assert stage_from_actions(r["actions"], r["latest_action"]) == "passed-one"
    both = r["actions"] + [{"date": "2026-04-01", "description": "Passed Senate", "classification": ["passage"], "chamber": "upper"}]
    assert stage_from_actions(both, "") == "passed-both"
    assert stage_from_actions(both + [{"date": "2026-05-01", "description": "Governor Approved", "classification": ["executive-signature"], "chamber": "executive"}], "") == "enacted"
    out, stats = update_bills([], [r], TAX, TODAY, backfill=True)
    assert len(out) == 1 and out[0]["stage"] == "passed-one" and out[0]["first_seen"] == "2026-01-15"
    assert {"sports-betting", "self-exclusion", "prediction-markets"} <= set(out[0]["topics"])
    # Irrelevant full-text hit ("gaming" as video games) is dropped.
    noise = dict(r, id="ocd-bill/2", title="Video game rating requirements for retailers", abstract="", subjects=[], actions=[])
    out2, stats2 = update_bills(out, [noise], TAX, TODAY, backfill=False)
    assert stats2["dropped_irrelevant"] == 1 and len(out2) == 1


def test_congress_convert_and_stage_text():
    bill = {"title": "SAFE Bet Act", "introducedDate": "2025-09-10", "latestAction": {"actionDate": "2025-09-10", "text": "Referred to the House Committee on Energy and Commerce."}, "sponsors": [{"fullName": "Rep. Tonko, Paul [D-NY-20]"}], "policyArea": {"name": "Sports and Recreation"}, "updateDate": "2026-10-01T00:00:00Z", "legislationUrl": "https://www.congress.gov/bill/119th-congress/house-bill/5284"}
    r = bills.convert_congress(bill, "119", "hr", "5284", "To establish a Federal framework for sports betting, and for other purposes.")
    assert r["id"] == "us-119-hr-5284" and r["identifier"] == "H.R. 5284" and r["session"] == "119th Congress"
    assert r["abstract"].startswith("To establish")
    out, stats = update_bills([], [r], TAX, TODAY, backfill=False)
    assert len(out) == 1 and out[0]["stage"] == "committee" and out[0]["level"] == "federal"
    assert stage_from_text(r["latest_action"]) == "committee"
    assert stage_from_text("Became Public Law No: 119-21.") == "enacted"
    assert stage_from_text("Passed/agreed to in House: On passage Passed by the Yeas and Nays: 300 - 100.") == "passed-one"
    assert stage_from_text("Presented to President.") == "passed-both"
    assert bills._PKG.match("BILLS-119hr5284ih").groups() == ("119", "hr", "5284", "ih")


CL_OPINION = {
    "cluster_id": 10561234, "caseName": "<mark>Kalshi</mark>, Inc. v. Hendrick", "court": "Court of Appeals for the Third Circuit", "court_id": "ca3", "court_jurisdiction": "F",
    "court_citation_string": "3rd Cir.", "dateFiled": "2026-09-30", "docketNumber": "25-1922", "citation": ["123 F.4th 456"], "status": "Published", "absolute_url": "/opinion/10561234/kalshi-v-hendrick/",
    "citeCount": 2, "opinions": [{"id": 1, "type": "010combined", "snippet": "whether sports <mark>event contracts</mark> are gaming under state law …"}],
}
CL_DOCKET = {
    "docket_id": 69000001, "caseName": "Polymarket v. State of Ohio", "court": "District Court, S.D. Ohio", "court_id": "ohsd", "dateFiled": "2026-08-01", "docketNumber": "2:26-cv-01234",
    "docket_absolute_url": "/docket/69000001/polymarket-v-ohio/", "cause": "28:1331 Federal Question", "suitNature": "890 Other Statutory Actions",
    "recap_documents": [{"description": "MOTION for Preliminary Injunction", "entry_date_filed": "2026-10-10", "absolute_url": "/docket/69000001/3/polymarket-v-ohio/"}],
}


def test_courtlistener_convert_and_levels():
    o = courts.convert_opinion(CL_OPINION)
    assert o["case_name"] == "Kalshi, Inc. v. Hendrick" and o["citation"] == "123 F.4th 456" and "<mark>" not in o["snippet"]
    assert o["url"].startswith("https://www.courtlistener.com/opinion/")
    d = courts.convert_docket(CL_DOCKET)
    assert d["kind"] == "docket" and d["documents"][0]["date"] == "2026-10-10"
    assert court_level("ca3", "F") == "federal-appellate" and court_level("scotus", "F") == "scotus"
    assert court_level("ohsd", "") == "federal-district" and court_level("ill", "S") == "state-supreme" and court_level("nysb", "") == "federal-bankruptcy"
    out, stats = update_cases([], [o, d], TAX, TODAY, backfill=True)
    assert len(out) == 2 and stats["dropped_irrelevant"] == 0
    docket = [c for c in out if c["kind"] == "docket"][0]
    assert docket["court_level"] == "federal-district" and docket["latest_activity"] == "2026-10-10" and "prediction-markets" in docket["topics"]
    # Noise: an opinion whose only hit is a metaphor or a surname is dropped.
    noise = courts.convert_opinion(dict(CL_OPINION, cluster_id=5, caseName="Smith v. Jones", opinions=[{"snippet": "the defendant took a <mark>gamble</mark> on a favorable verdict, see Charles W. Gamble, Evidence"}]))
    out2, stats2 = update_cases(out, [noise], TAX, TODAY, backfill=False)
    assert stats2["dropped_irrelevant"] == 1 and len(out2) == 2
    # A slip-and-fall suit against a casino (nature of suit 360) and a bankruptcy debtor named Casino are dropped.
    pi = courts.convert_docket(dict(CL_DOCKET, docket_id=7, caseName="Taylor v. Treasure Chest <mark>Casino</mark>, L.L.C.", suitNature="360 P.I.: Other", recap_documents=[]))
    debtor = courts.convert_docket(dict(CL_DOCKET, docket_id=8, caseName="Bryce <mark>Casino</mark>-Shells", court_id="nysb", suitNature="", cause="", recap_documents=[]))
    assert pi["matched"] == ["name"] and pi["suit_nature"].startswith("360")
    out3, stats3 = update_cases(out2, [pi, debtor], TAX, TODAY, backfill=False)
    assert stats3["dropped_irrelevant"] == 2 and len(out3) == 2
