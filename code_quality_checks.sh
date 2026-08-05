#!/bin/bash

# PAL MCP Server - Code Quality Checks
# This script runs all required linting and testing checks before committing changes.
# ALL checks must pass 100% for CI/CD to succeed.

# Deliberately NOT `set -e`. Under it the first failing check aborted the script,
# and the formatting checks run before the unit suite — so one misplaced space
# meant the 1000+ tests never ran and the agent learned nothing about whether its
# code worked (#79). Formatting is the cheapest, least informative check here;
# gating the most informative one behind it makes the gate useless exactly when
# there is real work to check.
#
# Instead every check records its outcome and the script fails at the end.
FAILED_CHECKS=()

# record <name> <exit-code> — remember a failure without abandoning the run.
record() {
    if [ "$2" -ne 0 ]; then
        FAILED_CHECKS+=("$1")
        echo "❌ $1: FAILED"
    else
        echo "✅ $1: passed"
    fi
}

echo "🔍 Running Code Quality Checks for PAL MCP Server"
echo "================================================="

# Determine Python command
if [[ -f ".pal_venv/bin/python" ]]; then
    PYTHON_CMD=".pal_venv/bin/python"
    PIP_CMD=".pal_venv/bin/pip"
    echo "✅ Using venv"
elif [[ -n "$VIRTUAL_ENV" ]]; then
    PYTHON_CMD="python"
    PIP_CMD="pip"
    echo "✅ Using activated virtual environment: $VIRTUAL_ENV"
else
    echo "❌ No virtual environment found!"
    echo "Please run: ./run-server.sh first to set up the environment"
    exit 1
fi
echo ""

# Check and install dev dependencies if needed
echo "🔍 Checking development dependencies..."
DEV_DEPS_NEEDED=false

# Check each dev dependency
for tool in ruff black isort pytest; do
    # Check if tool exists in venv or in PATH
    if [[ -f ".pal_venv/bin/$tool" ]] || command -v $tool &> /dev/null; then
        continue
    else
        DEV_DEPS_NEEDED=true
        break
    fi
done

if [ "$DEV_DEPS_NEEDED" = true ]; then
    echo "📦 Installing development dependencies..."
    $PIP_CMD install -q -r requirements-dev.txt
    echo "✅ Development dependencies installed"
else
    echo "✅ Development dependencies already installed"
fi

# Set tool paths
if [[ -f ".pal_venv/bin/ruff" ]]; then
    RUFF=".pal_venv/bin/ruff"
    BLACK=".pal_venv/bin/black"
    ISORT=".pal_venv/bin/isort"
    PYTEST=".pal_venv/bin/pytest"
else
    RUFF="ruff"
    BLACK="black"
    ISORT="isort"
    PYTEST="pytest"
fi
echo ""

# Step 1: Linting and Formatting
echo "📋 Step 1: Running Linting and Formatting Checks"
echo "--------------------------------------------------"

# These REPORT; they do not rewrite. A gate that edits your tree behind you is
# not a gate — it exits 0 having changed tracked files, and the next `git add -A`
# sweeps them into an unrelated commit. That happened twice on 2026-08-04, once
# carrying a settings change that had been explicitly rejected (#63).
# To fix what these report, run the same commands without --check/--check-only.

echo "🔍 Running ruff linting..."
$RUFF check --exclude test_simulation_files --exclude .pal_venv
record "Linting (ruff)" $?

echo "🎨 Checking black formatting..."
$BLACK . --check --exclude="test_simulation_files/" --exclude=".pal_venv/"
record "Formatting (black)" $?

echo "📦 Checking import sorting with isort..."
$ISORT . --check-only --skip-glob=".pal_venv/*" --skip-glob="test_simulation_files/*"
record "Import sorting (isort)" $?

echo ""

# Step 2: Unit Tests — reached even when the checks above failed, because they
# are the ones that tell you whether the code works.
echo "🧪 Step 2: Running Complete Unit Test Suite"
echo "---------------------------------------------"

echo "🏃 Running unit tests (excluding integration tests)..."
$PYTHON_CMD -m pytest tests/ -q -m "not integration"
record "Unit tests" $?
echo ""

# Step 3: Final Summary — the outcome is stated here, once, from what actually
# ran. The old version printed "PASSED" for all four unconditionally and relied
# on `set -e` never reaching it; that is only true while nothing fails, which is
# the one case the summary does not matter.
echo "=================================="
if [ ${#FAILED_CHECKS[@]} -gt 0 ]; then
    echo "❌ Code Quality Checks FAILED"
    echo "=================================="
    for check in "${FAILED_CHECKS[@]}"; do
        echo "   failed: $check"
    done
    echo ""
    echo "💡 For a formatting or import failure, run the same command without"
    echo "   --check / --check-only to fix it:"
    echo "     $BLACK . --exclude=\"test_simulation_files/\" --exclude=\".pal_venv/\""
    echo "     $ISORT . --skip-glob=\".pal_venv/*\" --skip-glob=\"test_simulation_files/*\""
    exit 1
fi

echo "🎉 All Code Quality Checks Passed!"
echo "=================================="
echo "✅ Linting (ruff) · Formatting (black) · Import sorting (isort) · Unit tests"
echo ""
echo "🚀 Your code is ready for commit and GitHub Actions!"
echo "💡 Remember to add simulator tests if you modified tools"