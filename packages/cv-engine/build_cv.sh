#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${CV_REPOSITORY_PATH:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BUILD_ROOT="$REPO_DIR/build"
DIST_ROOT="$REPO_DIR/dist"

# Keep the sources portable after moving the entry points out of the repository root.
export TEXINPUTS="$REPO_DIR:$REPO_DIR/vendor:$REPO_DIR/vendor/moderncv:$REPO_DIR/vendor/multibib:$REPO_DIR/content/shared:$REPO_DIR/content/academic:${TEXINPUTS:-}"
export BIBINPUTS="$REPO_DIR:$REPO_DIR/references/bibliography:${BIBINPUTS:-}"
export BSTINPUTS="$REPO_DIR:$REPO_DIR/vendor:$REPO_DIR/references/bibliography:${BSTINPUTS:-}"

KEYS=(
  academic-long
  industry-long
  senior-data-science
  ml-engineering
  applied-ai-llm
  technical-leadership
  analytics-decision-science
  research-scientific-ml
)

declare -A SOURCES=(
  [academic-long]="cv/long/academic/CV_academic_long.tex"
  [industry-long]="cv/long/industry/CV_industry_long.tex"
  [senior-data-science]="cv/short/senior-data-science/CV_senior_data_science.tex"
  [ml-engineering]="cv/short/ml-engineering/CV_ml_engineering.tex"
  [applied-ai-llm]="cv/short/applied-ai-llm/CV_applied_ai_llm.tex"
  [technical-leadership]="cv/short/technical-leadership/CV_technical_leadership.tex"
  [analytics-decision-science]="cv/short/analytics-decision-science/CV_analytics_decision_science.tex"
  [research-scientific-ml]="cv/short/research-scientific-ml/CV_research_scientific_ml.tex"
)

declare -A DIST_DIRS=(
  [academic-long]="long/academic"
  [industry-long]="long/industry"
  [senior-data-science]="short/senior-data-science"
  [ml-engineering]="short/ml-engineering"
  [applied-ai-llm]="short/applied-ai-llm"
  [technical-leadership]="short/technical-leadership"
  [analytics-decision-science]="short/analytics-decision-science"
  [research-scientific-ml]="short/research-scientific-ml"
)

usage() {
  printf 'Usage: %s {all|%s|file path/to/application.tex}\n' "$(basename "$0")" "${KEYS[*]}"
}

build_one() {
  local key="$1"
  local source_rel="${SOURCES[$key]}"
  local source_abs="$REPO_DIR/$source_rel"
  local source_dir
  local source_file
  local work_dir
  local pdf_name

  if [[ ! -f "$source_abs" ]]; then
    printf 'Missing source for %s: %s\n' "$key" "$source_rel" >&2
    return 1
  fi

  source_dir="$(dirname "$source_abs")"
  source_file="$(basename "$source_abs")"
  work_dir="$BUILD_ROOT/$key"
  pdf_name="${source_file%.tex}.pdf"
  mkdir -p "$work_dir" "$DIST_ROOT/${DIST_DIRS[$key]}"

  printf 'Building %-28s %s\n' "$key" "$source_rel"
  (
    cd "$source_dir"
    pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$work_dir" "$source_file" >/dev/null
  )

  if [[ "$key" == academic-long ]]; then
    for aux_name in Thesis Publications Preprint Collaborations Proceedings ProceedingsSSR Develop Books; do
      if [[ -f "$work_dir/$aux_name.aux" ]]; then
        (
          cd "$work_dir"
          bibtex "$aux_name" >/dev/null
        )
      fi
    done
    (
      cd "$source_dir"
      pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$work_dir" "$source_file" >/dev/null
      pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$work_dir" "$source_file" >/dev/null
    )
  else
    (
      cd "$source_dir"
      pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$work_dir" "$source_file" >/dev/null
    )
  fi

  if [[ ! -f "$work_dir/$pdf_name" ]]; then
    printf 'Expected PDF was not produced: %s\n' "$work_dir/$pdf_name" >&2
    return 1
  fi
  cp "$work_dir/$pdf_name" "$DIST_ROOT/${DIST_DIRS[$key]}/$pdf_name"
}

build_file() {
  local requested_path="$1"
  local source_abs
  local source_dir
  local source_file
  local work_dir
  local pdf_name
  local application_year

  if [[ "$requested_path" = /* ]]; then
    source_abs="$requested_path"
  else
    source_abs="$REPO_DIR/$requested_path"
  fi
  if [[ ! -f "$source_abs" ]]; then
    printf 'Missing application source: %s\n' "$requested_path" >&2
    return 1
  fi

  source_dir="$(dirname "$source_abs")"
  source_file="$(basename "$source_abs")"
  work_dir="$BUILD_ROOT/applications/${source_file%.tex}"
  pdf_name="${source_file%.tex}.pdf"
  application_year="$(date +%Y)"
  if [[ "${source_abs#$REPO_DIR/}" =~ ^cv/applications/([0-9]{4})/ ]]; then
    application_year="${BASH_REMATCH[1]}"
  fi
  mkdir -p "$work_dir" "$DIST_ROOT/applications/$application_year"

  printf 'Building application             %s\n' "${source_abs#$REPO_DIR/}"
  for _ in 1 2; do
    (
      cd "$source_dir"
      pdflatex -interaction=nonstopmode -halt-on-error -output-directory="$work_dir" "$source_file" >/dev/null
    )
  done
  cp "$work_dir/$pdf_name" "$DIST_ROOT/applications/$application_year/$pdf_name"
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

case "$1" in
  all)
    for key in "${KEYS[@]}"; do
      build_one "$key"
    done
    ;;
  academic-long|industry-long|senior-data-science|ml-engineering|applied-ai-llm|technical-leadership|analytics-decision-science|research-scientific-ml)
    [[ $# -eq 1 ]] || { usage >&2; exit 2; }
    build_one "$1"
    ;;
  file)
    [[ $# -eq 2 ]] || { printf 'Usage: %s file path/to/application.tex\n' "$(basename "$0")" >&2; exit 2; }
    build_file "$2"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
