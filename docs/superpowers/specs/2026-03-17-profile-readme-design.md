# Profile README Design

## Summary
- Document the GitHub profile README for LeePepe such that it matches the provided markdown block (intro badge, stack badges, project table, stats widgets) while keeping formatting consistent and easy to maintain.

## Requirements
1. Mirror the supplied markdown sections (intro text, stacks, project table, stats images) so the profile renders the same as what was shared in the request.
2. Store the content in `README.md` at the repository root since this repository is the GitHub profile repo.
3. Keep the layout minimal—no additional prose or sections beyond what was requested.
4. Ensure the file uses valid Markdown (conversion of table, inline HTML, and image badges as provided).

## Constraints
- No existing README content to preserve; the repository only contains `.git` and is otherwise empty.
- Remote URL is not configured locally (we will need to learn the GitHub repo URL or new remote before pushing).
- README should be written in ASCII where the supplied text is already ASCII; no extra Unicode is required.

## Proposed Approach
1. Create `README.md` that copies the provided markdown verbatim, preserving the central `div` block, table, and badges.
2. Keep the intro content, stack badge rows, project table, and stats GIFs as separate blocks with the same order.

## Layout Breakdown
1. **Hero Section**: `<div align="center">` block with heading, roles, and GitHub/LinkedIn badges.
2. **Stack Badges**: A horizontal line followed by badges for Swift, SwiftUI, TypeScript, Python, Xcode, VS Code, Core ML, MCP.
3. **Projects Table**: Markdown table with project links and descriptions.
4. **Stats Widgets**: Two `github-readme-stats` images stacked in a center-aligned `div`.

## Reference Markdown
The README needs to embed the following content exactly (including badges, table, and stats links). This is copied verbatim from the user request:

```html
<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=IBM+Plex+Mono&weight=600&size=22&duration=3500&pause=1500&color=7C6AF7&center=true&vCenter=true&width=480&lines=I+build+apps+that+think.;iOS+%40+Microsoft.;voice+%C2%B7+AI+tools+%C2%B7+MCP." alt="" />

<br/>

iOS engineer at **Microsoft** · AI tools builder on the side

<br/>

[![GitHub](https://img.shields.io/badge/GitHub-LeePepe-181717?style=flat-square&logo=github)](https://github.com/LeePepe)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-connect-0A66C2?style=flat-square&logo=linkedin)](https://linkedin.com/in/leepepe)

</div>

---

### stack

![Swift](https://img.shields.io/badge/Swift-F05138?style=flat-square&logo=swift&logoColor=white)
![SwiftUI](https://img.shields.io/badge/SwiftUI-0070C9?style=flat-square&logo=swift&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Xcode](https://img.shields.io/badge/Xcode-1575F9?style=flat-square&logo=xcode&logoColor=white)
![VS Code](https://img.shields.io/badge/VS_Code-007ACC?style=flat-square&logo=visualstudiocode&logoColor=white)
![Core ML](https://img.shields.io/badge/Core_ML-000000?style=flat-square&logo=apple&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-7C6AF7?style=flat-square&logoColor=white)

---

### projects

| project | description |
|---|---|
| [**VoxPocket**](https://github.com/LeePepe/VoxPocket) | Voice-to-text for macOS/iOS · AI refinement via Apple Intelligence · deterministic undo/redo |
| [**Helix**](https://github.com/LeePepe/Helix) | VS Code extension · compare Figma designs vs code · generate production components |
| [**CodeAnalyzer**](https://github.com/LeePepe/CodeAnalyzer) | VS Code extension · LLM-powered PR analysis for GitHub & Azure DevOps |
| [**xcode-mcp-server**](https://github.com/LeePepe/xcode-mcp-server) | MCP server · deep Xcode integration for AI assistants |

---

<div align="center">
<img height="150" src="https://github-readme-stats.vercel.app/api?username=LeePepe&show_icons=true&theme=github_dark&hide_border=true&hide_title=true&count_private=true" />
<img height="150" src="https://github-readme-stats.vercel.app/api/top-langs/?username=LeePepe&layout=compact&theme=github_dark&hide_border=true&langs_count=6" />
</div>
```

## Testing & Validation
- Preview the README locally (e.g., GitHub preview or quick view) to ensure Markdown renders as expected.
- Run `git status` to confirm only `README.md` and spec/plan docs changed besides metadata files.

## Risks / Notes
- If the user wants restructuring, we will revisit the design; right now we assume they want the provided layout verbatim until told otherwise.
- Remote configuration is missing, so pushing requires additional information.

## Review Checklist
- [ ] Spec matches user-provided markdown and clarifications.
- [ ] README file path/root is correct.
- [ ] Any temporary notes removed before final commit (if present at first pass).

## Next Steps
1. Get spec reviewed via `spec-document-reviewer` subagent.
2. Ask the user to approve the spec file.
3. Run `writing-plans` skill to create the implementation plan.
