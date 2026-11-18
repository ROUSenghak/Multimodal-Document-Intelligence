# Both-agent project skills

This ZIP is structured for extraction **at your project root**. It includes two identical sets of skills so both Claude Code and Codex can discover them using their own project conventions.

## Install

From a terminal, run:

    unzip /path/to/claude-codex-project-skills.zip -d /path/to/your-project

Or extract the ZIP and copy the two hidden directories (`.claude` and `.agents`) into your project root.

## Contents

- `.claude/skills/learning-first-coding/SKILL.md`
- `.claude/skills/research-paper-reading/SKILL.md`
- `.agents/skills/learning-first-coding/SKILL.md`
- `.agents/skills/research-paper-reading/SKILL.md`

## Usage

- Research-paper analysis: request the `research-paper-reading` skill.
- Coding and debugging: request the `learning-first-coding` skill.
- Implementing published research: ask for both skills, starting with paper analysis.

Skills are discovered based on their descriptions. Explicitly naming a skill is helpful for ensuring it is used.

## Maintenance

There are two physical copies of each SKILL.md. When editing a skill, update the matching file in both agent directories so behavior remains consistent. Do not assume modifications to one copy automatically update the other.
