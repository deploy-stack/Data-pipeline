from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import streamlit as st

from agent_tools import profile_to_student
from match import rank_programs
from orchestrator_agent import run_agentic_pipeline
from profile_parser import parse_user_profile_text
from schema import Program, StudentProfile


JSON_PATH = Path("data/programs.json")
CSV_PATH = Path("data/programs.csv")
INTEREST_OPTIONS = ["computer science", "AI", "engineering", "math", "biology", "business"]
MODALITY_OPTIONS = ["online", "in_person", "hybrid"]


@st.cache_data
def load_programs() -> list[Program]:
    """Load the verified offline snapshot for recommendation matching."""
    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return [Program.from_dict(record) for record in records]


@st.cache_data
def load_rows() -> list[dict]:
    """Load CSV rows for the optional dataset explorer."""
    with CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def format_list(items: list[str]) -> str:
    return ", ".join(items) if items else "None"


def format_subjects(subjects: list[str]) -> str:
    return ", ".join(subjects) if subjects else "Not listed"


def render_recommendation(index: int, item: dict) -> None:
    program = item["program"]
    reasons = "; ".join(item.get("reasons", [])) or "Good overall fit for the selected profile."

    with st.container(border=True):
        st.markdown(f"### {index}. {program.program_name}")
        st.caption(f"{program.provider} | Match score: {item['score']}")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Subjects:** {format_subjects(program.subject_areas)}")
            st.write(f"**Program type:** {program.program_type or program.modality}")
            st.write(f"**Location:** {program.location or 'Not listed'}")
            st.write(f"**Cost:** {program.cost or 'Needs follow-up'}")
        with col2:
            st.write(f"**Deadline:** {program.application_deadline or 'Needs follow-up'}")
            st.write(f"**Matched interests:** {format_list(item.get('matched_interests', []))}")
            st.write(f"**Unmatched interests:** {format_list(item.get('unmatched_interests', []))}")

        st.write(f"**Why it matches:** {reasons}")
        st.link_button("Open source page", program.source_url)


def pipeline_step(message: str, progress_value: float, progress, status, stage_box) -> None:
    stage_box.info(f"Current stage: {message}")
    status.write(message)
    progress.progress(progress_value)
    time.sleep(0.35)


def show_pipeline_status(used_firecrawl: bool) -> None:
    st.markdown("**Pipeline status:**")
    st.write(":heavy_check_mark: sources discovered")
    st.write(":heavy_check_mark: data extracted")
    st.write(":heavy_check_mark: schema validated")
    st.write(":heavy_check_mark: match index built")
    if used_firecrawl:
        st.caption("Live Firecrawl pipeline was used for discovery and extraction.")
    else:
        st.caption("Used bundled verified snapshot as an offline fallback.")


REQUIRED_DATASET_FIELDS = [
    "program_name",
    "duration",
    "cost",
    "eligibility_requirements",
    "application_deadline",
    "provider",
]


def rows_from_records(records: list[dict]) -> list[dict]:
    rows = []
    for record in records:
        subjects = record.get("subject_areas", "")
        if isinstance(subjects, list):
            subjects = "; ".join(subjects)
        rows.append(
            {
                "program_name": record.get("program_name", ""),
                "duration": record.get("duration", ""),
                "cost": record.get("cost", ""),
                "eligibility_requirements": record.get("eligibility_requirements", ""),
                "application_deadline": record.get("application_deadline", ""),
                "provider": record.get("provider", ""),
                "program_type": record.get("program_type") or record.get("modality", ""),
                "location": record.get("location", ""),
                "subjects": subjects,
                "modality": record.get("modality", ""),
                "confidence_score": record.get("confidence_score", ""),
                "source": record.get("source", ""),
            }
        )
    return rows


def is_record_complete(record: dict, profile: dict) -> bool:
    for field in REQUIRED_DATASET_FIELDS:
        if not record.get(field):
            return False

    if profile.get("preferred_modality") == "in_person":
        return bool(record.get("location"))

    return True


def split_complete_records(records: list[dict], profile: dict) -> tuple[list[dict], list[dict]]:
    complete = []
    incomplete = []
    for record in records:
        if is_record_complete(record, profile):
            complete.append(record)
        else:
            incomplete.append(record)
    return complete, incomplete


def show_final_metrics(metrics: dict) -> None:
    st.subheader("Final Output Metrics")
    col1, col2, col3 = st.columns(3)
    col1.metric("Data sources explored", metrics.get("sources_explored", 0))
    col2.metric("Data points extracted", metrics.get("data_points_extracted", 0))
    col3.metric("Records verified against user details", metrics.get("records_verified_against_user_details", 0))


def main() -> None:
    st.set_page_config(page_title="Pre-College Program Matcher", layout="wide")
    st.title("Pre-College Program Matcher")
    st.write(
        "Enter a student profile, run the agentic Firecrawl pipeline, then generate "
        "personalized pre-college program recommendations."
    )

    if not JSON_PATH.exists():
        st.error("Missing data/programs.json. Run `python demo.py` to rebuild the offline snapshot.")
        return

    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None
    if "show_recommendations" not in st.session_state:
        st.session_state.show_recommendations = False

    st.subheader("Student profile")
    input_mode = st.radio(
        "Choose input method",
        ["Option 1 - Structured input", "Option 2 - Unstructured input"],
        horizontal=True,
    )

    if input_mode.startswith("Option 1"):
        col1, col2 = st.columns(2)
        with col1:
            grade = st.selectbox("Grade", options=[8, 9, 10, 11, 12], index=3)
            interests = st.multiselect(
                "Interests",
                options=INTEREST_OPTIONS,
                default=["computer science", "AI", "engineering"],
            )
        with col2:
            preferred_modality = st.selectbox("Preferred modality", options=MODALITY_OPTIONS)
            budget_max = st.number_input(
                "Max budget",
                min_value=0,
                max_value=30000,
                value=4000,
                step=250,
                format="%d",
            )
        st.markdown("**Location preference**")
        loc_col1, loc_col2, loc_col3 = st.columns(3)
        with loc_col1:
            location_preference = st.text_input("City or area", value="", placeholder="Phoenix, AZ")
        with loc_col2:
            radius_miles = st.slider("Search radius", min_value=10, max_value=500, value=50, step=10)
        with loc_col3:
            include_online = st.checkbox("Include online programs", value=True)
        st.caption("💡 **Location matching:** Online programs can be attended from anywhere. In-person programs must match your specified location.")
        profile = {
            "grade": int(grade),
            "interests": interests,
            "preferred_modality": preferred_modality,
            "budget_max": int(budget_max),
            "location_preference": location_preference,
            "radius_miles": int(radius_miles),
            "include_online": include_online,
        }
    else:
        user_text = st.text_area(
            "Describe the student profile",
            value="I am a grade 11 student interested in AI and engineering, prefer online programs under $4000, near Phoenix within 100 miles.",
        )
        profile = parse_user_profile_text(user_text)
        interests = profile["interests"]
        st.caption(
            "Extracted profile: "
            f"grade {profile['grade']}, interests {format_list(profile['interests'])}, "
            f"preferred modality {profile['preferred_modality']}, budget ${profile['budget_max']:,}, "
            f"location {profile.get('location_preference') or 'any'}, "
            f"radius {profile.get('radius_miles')} miles, "
            f"online {'included' if profile.get('include_online') else 'not included'}"
        )

    use_firecrawl = st.checkbox("Use Firecrawl live internet discovery and extraction", value=True)
    source_limit = st.slider("Sources to inspect", min_value=2, max_value=100, value=5)

    if not interests:
        st.info("Please select at least one interest to generate personalized recommendations.")

    run_disabled = not interests
    if st.button("Run pipeline", type="primary", disabled=run_disabled):
        st.session_state.show_recommendations = False
        progress = st.progress(0)
        status = st.empty()
        stage_box = st.empty()
        pipeline_step("Agent 1: collecting profile and searching Firecrawl for relevant sources...", 0.2, progress, status, stage_box)
        pipeline_step("Agent 2: extracting structured program fields from discovered sources...", 0.45, progress, status, stage_box)
        pipeline_step("Agent 3: verifying completeness, deadlines, eligibility, costs, and location fit...", 0.7, progress, status, stage_box)
        pipeline_step("Building match-ready index for this profile...", 0.9, progress, status, stage_box)
        try:
            with st.spinner("Running agents..."):
                st.session_state.pipeline_result = run_agentic_pipeline(
                    profile,
                    use_firecrawl=use_firecrawl,
                    source_limit=source_limit,
                    extraction_limit=source_limit,
            )
            progress.progress(1.0)
            stage_box.success("Current stage: done")
            status.success("Pipeline complete. Match-ready dataset generated.")
        except Exception as exc:
            st.session_state.pipeline_result = None
            status.error(str(exc))
            st.error(
                "Live internet discovery needs a valid Firecrawl key in `.env`. "
                "Set `FIRECRAWL_API_KEY=...`, then run the pipeline again."
            )

    result = st.session_state.pipeline_result
    if result is None:
        st.info("Run the pipeline before viewing the dataset or generating recommendations.")
        return

    show_pipeline_status(result.used_firecrawl)
    for message in result.messages:
        st.caption(message)
    show_final_metrics(result.metrics)

    if result.sources:
        with st.expander("Discovered sources"):
            st.dataframe(result.sources)

    find_disabled = not interests
    if st.button("Find Programs", disabled=find_disabled):
        st.session_state.show_recommendations = True

    if st.session_state.show_recommendations:
        programs = [Program.from_dict(record) for record in result.records]
        matches = rank_programs(programs, profile_to_student(profile), limit=len(programs))
        top_matches = [item for item in matches if item["score"] > 0][:5]
        lower_fit = [item for item in matches if item["score"] <= 0]

        st.subheader("Top Recommended Programs")
        if len(top_matches) < 5:
            st.info("We found only a few strong matches for this profile based on the current dataset.")
        if not top_matches:
            st.warning("No strong matches were found. Try broadening interests or modality.")
        for index, item in enumerate(top_matches, start=1):
            render_recommendation(index, item)

        if lower_fit:
            with st.expander("Lower-Fit Options"):
                st.write(
                    "These programs meet some general constraints but have weak interest alignment "
                    "for the selected profile."
                )
                for index, item in enumerate(lower_fit, start=1):
                    render_recommendation(index, item)
    else:
        st.info("Click Find Programs to rank the match-ready dataset for this student.")

    st.subheader("Verified program dataset (structured output from pipeline)")
    complete_records, incomplete_records = split_complete_records(result.records, profile)

    with st.expander(f"Complete records ({len(complete_records)})"):
        st.write(
            "Records with non-null program_name, duration, cost, eligibility_requirements, "
            "application_deadline, and provider. For in-person student profiles, location is also required."
        )
        st.dataframe(rows_from_records(complete_records))

    with st.expander(f"Incomplete records ({len(incomplete_records)})"):
        st.write(
            "Records missing one or more required fields. This view helps identify gaps in the structured dataset."
        )
        st.dataframe(rows_from_records(incomplete_records))


if __name__ == "__main__":
    main()
