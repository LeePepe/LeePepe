# Profile README Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a GitHub profile `README.md` that exactly mirrors the markdown snippet supplied in the spec so the personal site renders the requested layout.

**Architecture:** The README is a single Markdown document that reproduces the hero badge block, stack badge row, projects table, and stats widgets from the spec; no additional logic or dependencies are introduced.

**Tech Stack:** Markdown, standard Unix tooling (`cat`, shell redirection), Git (status/diff/add/commit/push).

---

### Task 1: Write profile README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Draft README content**

```bash
cat <<'EOF' > README.md
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
EOF
```

- [ ] **Step 2: Confirm README matches spec**

```bash
git status --short README.md && git diff README.md
```

Verify no formatting drift from the spec-provided block, correcting any mismatch before the next step.

- [ ] **Step 3: Stage README**

```bash
git add README.md
```

- [ ] **Step 4: Commit README**

```bash
git commit -m "feat: add profile README matching request"
```

Ensure the commit includes the spec and plan files already created earlier.

### Task 2: Publish to GitHub

**Files:**
- None

- [ ] **Step 1: Configure upstream remote**

```bash
git remote add origin https://github.com/LeePepe/LeePepe.git
```

If the remote already exists, verify the URL with `git remote get-url origin` and update as needed.

- [ ] **Step 2: Push branch**

```bash
git push -u origin main
```

Confirm the push succeeds and the profile repo shows the new README.

- [ ] **Step 3: Verify remote status**

```bash
git remote show origin
```

Check that `main` is tracking `origin/main` with the expected URL.
