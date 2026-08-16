# OpenClink: หลายเวิร์กโฟลว์ บริบทเดียว

**🇹🇭 ภาษาไทย · 🇬🇧 [English](README.en.md)**

> **นี่คือ fork** ของ [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server) (ต้นทางหยุดดูแลตั้งแต่ ~กลางปี 2026) โดยเพิ่มแบบ additive ล้วน ไม่แตะพฤติกรรมเดิม:
> - **`antigravity`** — clink agent สำหรับ Antigravity CLI (`agy`) ตัวสืบทอดจาก Gemini CLI ของ Google ขับผ่าน Windows ConPTY
> - **`cursor`** — clink agent สำหรับ `cursor-agent` ของ Cursor เปิดทางไปยังตระกูลโมเดลที่ client อื่นไม่มี (Grok ของ xAI, Kimi ของ Moonshot, GLM ของ Zhipu, Composer)
> - **`opencode`** — clink agent สำหรับ [OpenCode](https://opencode.ai) CLI · เป็นตัวเดียวที่ **รายงานค่าใช้จ่ายของการเรียกมาเอง** (`part.cost`) และตัวเดียวที่เข้าถึง provider `opencode-go` ได้ (deepseek, GLM, Kimi, MiniMax, Qwen, Grok)
> - **`claude-9arm`** — config ตัวอย่างชี้ Claude Code CLI ไปยัง model gateway ทางเลือก
> - **override `model` / `reasoning_effort` ต่อ call** ของ clink (Codex ใช้ `-m` + effort; ตัวอื่นใช้ `--model`)
> - **แก้บั๊ก** — `images` เดิมถูกรับไว้แล้วทิ้งเงียบ ๆ (ไม่มี runner ตัวไหนใช้เลย) ตอนนี้ error พร้อมบอกวิธีที่ได้ผลจริง · pin `mcp<2` เพราะ 2.x ถอด `Server.list_tools` ทำให้ server ตายตั้งแต่ import
>
> รายละเอียด: [CHANGES-FORK.md](CHANGES-FORK.md) และ [คู่มือ clink model/effort](docs/clink-model-effort-guide.md) — ส่วนอื่นเหมือน upstream ทุกอย่าง

<div align="center">

  <em>CLI เดียว เชื่อมทุกโมเดล ด้วย clink</em><br />
  <sub><a href="docs/name-change.md">เดิมชื่อ PAL MCP และก่อนหน้านั้นคือ Zen MCP</a></sub>

  [OpenClink in action](https://github.com/user-attachments/assets/0d26061e-5f21-4ab1-b7d0-f883ddc2c3da)

👉 **[ดูตัวอย่างเพิ่มเติม](#-ดูเครื่องมือทำงานจริง)**

### CLI ที่คุณใช้ + หลายโมเดล = ทีมพัฒนา AI ของคุณ

**ใช้ 🤖 CLI ที่คุณถนัด:**
[Claude Code](https://www.anthropic.com/claude-code) · [Codex CLI](https://github.com/openai/codex) · [Antigravity (`agy`)](https://antigravity.google) · [Qwen Code CLI](https://qwenlm.github.io/qwen-code-docs/) · [Cursor](https://cursor.com) · _และอื่น ๆ_

**พร้อมหลายโมเดลในพรอมป์ตเดียว:**
Gemini · OpenAI · Anthropic · Grok · Azure · Ollama · OpenRouter · DIAL · โมเดลบนเครื่อง

</div>

---

## 🆕 มีสะพาน CLI-to-CLI แล้ว

เครื่องมือ **[`clink`](docs/tools/clink.md)** (CLI + Link) เชื่อม AI CLI ภายนอกเข้ามาในเวิร์กโฟลว์คุณโดยตรง:

- **เชื่อม CLI ภายนอก** เช่น Codex CLI, Antigravity (`agy`), Claude Code เข้ามาในงานได้เลย
- **CLI Subagents** — เปิด CLI แยก isolated จาก _ภายใน_ CLI ปัจจุบัน! Claude Code เปิด subagent เป็น Codex ได้ Codex เปิด subagent เป็นตัวอื่นได้ โยนงานหนัก (code review, ล่าบั๊ก) ไปยัง context ใหม่ ให้ context หลักของคุณไม่รก — subagent คืนแค่ผลสุดท้าย
- **Context Isolation** — สืบสวนแยกกันได้โดยไม่ปน workspace หลัก
- **Role เฉพาะทาง** — เปิด agent ในบท `planner`, `codereviewer` หรือ role ที่คุณตั้งเอง พร้อม system prompt เฉพาะ
- **ความสามารถ CLI เต็มรูปแบบ** — web search, อ่านไฟล์, ใช้ MCP tool, ค้นเอกสารล่าสุด
- **ต่อเนื่องไร้รอยต่อ** — sub-CLI เป็นสมาชิกชั้นหนึ่งของบทสนทนา บริบทไหลข้ามเครื่องมือ

```bash
# Codex เปิด subagent เป็น Codex เพื่อ review แยกใน context ใหม่
clink with codex codereviewer to audit auth module for security issues

# หาข้อสรุปจากหลายโมเดล → ส่งต่อให้ลงมือ โดยคงบริบทเต็มระหว่างเครื่องมือ
Use consensus with gpt-5 and gemini-pro to decide: dark mode or offline support next
Continue with clink codex - implement the recommended feature
```

**เลือก model + reasoning ต่อ call ได้ (ของ fork นี้):**
```
clink codex model="gpt-5.6-sol"  reasoning_effort="max"   → งาน leaf ที่ยากสุด (ฉลาดสุด)
clink codex model="gpt-5.6-luna" reasoning_effort="high"  → งานประหยัด quota
clink antigravity model="Claude Opus 4.6 (Thinking)"      → ขอความเห็นนอกค่าย OpenAI
```

👉 **[เรียนรู้ clink เพิ่มเติม](docs/tools/clink.md)** · **[คู่มือ model/effort](docs/clink-model-effort-guide.md)**

---

## ทำไมต้อง OpenClink?

**ในเมื่อคุณสั่งการทุกโมเดลพร้อมกันได้ ทำไมต้องพึ่งโมเดลเดียว?**

OpenClink เป็นเซิร์ฟเวอร์ Model Context Protocol ที่เสริมพลังเครื่องมืออย่าง [Claude Code](https://www.anthropic.com/claude-code), [Codex CLI](https://developers.openai.com/codex/cli) และ IDE เช่น [Cursor](https://cursor.com) — **เชื่อมเครื่องมือ AI ที่คุณชอบเข้ากับหลายโมเดล** เพื่อวิเคราะห์โค้ด แก้ปัญหา และพัฒนาแบบร่วมมือกันได้ลึกขึ้น

### ร่วมมือกับ AI จริง ด้วยบริบทที่ต่อเนื่อง

OpenClink รองรับ **conversation threading** — CLI ของคุณจึงถกไอเดียกับหลายโมเดล แลกเหตุผล ขอ second opinion หรือจัดดีเบตระหว่างโมเดลได้ CLI ของคุณคุมทุกอย่าง แต่ได้มุมมองจาก AI ที่เหมาะกับแต่ละงานย่อย บริบทไหลต่อข้ามเครื่องมือ/โมเดล เปิดทางเวิร์กโฟลว์ซับซ้อน เช่น review หลายโมเดล → วางแผน → ลงมือ → ตรวจก่อน commit

> **คุณคือคนคุม** — CLI ของคุณสั่งการทีม AI แต่คุณตัดสินใจเวิร์กโฟลว์เอง เขียนพรอมป์ตให้ดึง Gemini Pro, GPT-5, Flash หรือโมเดลบนเครื่องมาใช้ตอนที่ต้องการ

<details>
<summary><b>เหตุผลที่ควรใช้ OpenClink</b></summary>

- **Multi-Model Orchestration** — ประสานหลายโมเดล (Gemini Pro, O3, GPT-5 และ 50+ โมเดล) เลือกตัวที่เหมาะกับแต่ละงาน
- **Context Revival** — แม้ context ของ CLI หลักจะรีเซ็ต ก็ให้โมเดลอื่น "เตือนความจำ" เพื่อคุยต่อได้ไร้รอยต่อ
- **Guided Workflows** — บังคับขั้นตอนสืบสวนอย่างเป็นระบบ กันการวิเคราะห์แบบรีบร้อน
- **Extended Context** — ทะลุขีดจำกัดด้วยการโยนไปโมเดล context ใหญ่สำหรับ codebase ขนาดมหึมา
- **Conversation Continuity** — บริบทเต็มไหลข้ามเครื่องมือและโมเดล
- **จุดแข็งเฉพาะโมเดล** — thinking กับ Gemini Pro, ความเร็วกับ Flash, เหตุผลกับ O3, ความเป็นส่วนตัวกับ Ollama บนเครื่อง
- **Code Review มืออาชีพ** — วิเคราะห์หลายรอบ พร้อมระดับความรุนแรงและ feedback ที่ลงมือได้
- **Debug อัจฉริยะ** — หา root cause อย่างเป็นระบบ พร้อมติดตามสมมติฐาน + ระดับความมั่นใจ
- **เลือกโมเดลอัตโนมัติ** — ระบบเลือกโมเดลที่เหมาะกับแต่ละงานย่อย (หรือคุณระบุเองก็ได้)
- **Vision** — วิเคราะห์ภาพหน้าจอ ไดอะแกรม เนื้อหาภาพด้วยโมเดล vision
- **โมเดลบนเครื่อง** — รัน Llama / Mistral ในเครื่องเพื่อความเป็นส่วนตัวและไม่มีค่า API
- **ข้ามลิมิต token ของ MCP** — จัดการพรอมป์ต/คำตอบขนาดใหญ่เกิน 25K อัตโนมัติ

**ฟีเจอร์เด็ด:** เมื่อ context ของ CLI หลักรีเซ็ต แค่สั่ง "continue with O3" — คำตอบของอีกโมเดลจะปลุกความเข้าใจกลับมาโดยไม่ต้องป้อนเอกสารซ้ำ

</details>

#### AI Stack ที่แนะนำ

<details>
<summary>สำหรับผู้ใช้ Claude Code</summary>

- **Sonnet 4.5** — งาน agentic + orchestration ทั้งหมด
- **Gemini 3.0 Pro** หรือ **GPT-5.2 / Pro** — คิดเชิงลึก, review เพิ่ม, debug/validate, ตรวจก่อน commit
</details>

<details>
<summary>สำหรับผู้ใช้ Codex</summary>

- **GPT-5.2 Codex Medium** — งาน agentic + orchestration ทั้งหมด
- **Gemini 3.0 Pro** หรือ **GPT-5.2-Pro** — คิดเชิงลึก, review เพิ่ม, debug/validate, ตรวจก่อน commit
</details>

## เริ่มใช้งาน (5 นาที)

**ต้องมีก่อน:** Python 3.10+, Git, [ติดตั้ง uv](https://docs.astral.sh/uv/getting-started/installation/)

**1. เตรียม API Key** (เลือกอย่างน้อยหนึ่ง): [OpenRouter](https://openrouter.ai/) · [Gemini](https://makersuite.google.com/app/apikey) · [OpenAI](https://platform.openai.com/api-keys) · [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/) · [X.AI](https://console.x.ai/) · [DIAL](https://dialx.ai/) · [Ollama](https://ollama.ai/) (ฟรี บนเครื่อง)

**2. ติดตั้ง** (เลือกอย่างใดอย่างหนึ่ง):

**ตัวเลือก A: clone + ตั้งค่าอัตโนมัติ** (แนะนำ)
```bash
# fork นี้ (เพิ่ม antigravity / claude-9arm / model+effort ต่อ call)
git clone https://github.com/xenodeve/openclink.git
cd openclink

# จัดการให้หมด: setup, config, API key จาก environment
# ตั้งค่าให้ Claude Desktop, Claude Code, Codex CLI, Qwen CLI อัตโนมัติ (Gemini CLI ปลดระวางแล้ว → ใช้ Antigravity)
./run-server.sh
```

**ตัวเลือก B: ติดตั้งทันทีด้วย [uvx](https://docs.astral.sh/uv/getting-started/installation/)**
```json
// เพิ่มใน ~/.claude/settings.json หรือ .mcp.json — อย่าลืมใส่ API key ใต้ env
{
  "mcpServers": {
    "openclink": {
      "command": "bash",
      "args": ["-c", "for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x \"$p\" ] && exec \"$p\" --from git+https://github.com/xenodeve/openclink.git openclink; done; echo 'uvx not found' >&2; exit 1"],
      "env": {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:~/.local/bin",
        "GEMINI_API_KEY": "your-key-here",
        "DISABLED_TOOLS": "analyze,refactor,testgen,secaudit,docgen,tracer",
        "DEFAULT_MODEL": "auto"
      }
    }
  }
}
```

**3. เริ่มใช้!**
```
"ใช้ openclink วิเคราะห์โค้ดนี้หาช่องโหว่ความปลอดภัยด้วย gemini pro"
"debug error นี้ด้วย o3 แล้วให้ flash แนะนำการ optimize"
"clink with cli_name=\"antigravity\" role=\"planner\" ช่วยร่างแผน rollout แบบเป็นเฟส"
```

👉 **[คู่มือ setup ฉบับเต็ม](docs/getting-started.md)** · 👉 **[ตั้งค่า Cursor & VS Code](docs/getting-started.md#ide-clients)** · 📺 **[ดูตัวอย่างจริง](#-ดูเครื่องมือทำงานจริง)**

## Core Tools (เครื่องมือหลัก)

> **หมายเหตุ:** แต่ละ tool มีเวิร์กโฟลว์/พารามิเตอร์/คำอธิบายของตัวเองที่กิน context แม้ไม่ได้ใช้ บางตัวจึงปิดไว้โดยดีฟอลต์ ดู [Tool Configuration](#tool-configuration)

**การร่วมมือ & วางแผน** *(เปิดโดยดีฟอลต์)*
- **[`clink`](docs/tools/clink.md)** — สะพานส่งงานไป AI CLI ภายนอก (planner, codereviewer ฯลฯ)
- **[`chat`](docs/tools/chat.md)** — ระดมสมอง, ขอ second opinion, ตรวจแนวทาง
- **[`thinkdeep`](docs/tools/thinkdeep.md)** — คิดเชิงลึก, วิเคราะห์ edge case, มุมมองทางเลือก
- **[`planner`](docs/tools/planner.md)** — แตกงานซับซ้อนเป็นแผนที่ลงมือได้
- **[`consensus`](docs/tools/consensus.md)** — ขอความเห็นผู้เชี่ยวชาญจากหลายโมเดล พร้อมกำหนดจุดยืน

**วิเคราะห์ & คุณภาพโค้ด**
- **[`debug`](docs/tools/debug.md)** — สืบสวนหา root cause อย่างเป็นระบบ
- **[`precommit`](docs/tools/precommit.md)** — ตรวจการเปลี่ยนแปลงก่อน commit กัน regression
- **[`codereview`](docs/tools/codereview.md)** — review มืออาชีพพร้อมระดับความรุนแรง
- **[`analyze`](docs/tools/analyze.md)** *(ปิดโดยดีฟอลต์)* — เข้าใจสถาปัตยกรรม/รูปแบบ/dependency ทั้ง codebase

**เครื่องมือพัฒนา** *(ปิดโดยดีฟอลต์)*
- **[`refactor`](docs/tools/refactor.md)** · **[`testgen`](docs/tools/testgen.md)** · **[`secaudit`](docs/tools/secaudit.md)** · **[`docgen`](docs/tools/docgen.md)**

**ยูทิลิตี้**
- **[`apilookup`](docs/tools/apilookup.md)** — บังคับค้นเอกสาร API/SDK ปีปัจจุบันใน sub-process กันคำตอบจากข้อมูลเก่า
- **[`challenge`](docs/tools/challenge.md)** — กันคำตอบ "You're absolutely right!" ด้วยการวิเคราะห์เชิงวิพากษ์
- **[`selectagents`](docs/tools/selectagents.md)** — คำนวณแผนการมอบงานจากข้อมูลโมเดลที่วัดแล้ว แทนการนึกเอา (⚠️ ยังเป็น stub ดู #96)
- **[`tracer`](docs/tools/tracer.md)** *(ปิดโดยดีฟอลต์)* — วิเคราะห์ call-flow แบบ static

<details>
<summary><b id="tool-configuration">👉 Tool Configuration</b></summary>

เปิดโดยดีฟอลต์: `chat`, `thinkdeep`, `planner`, `consensus`, `codereview`, `precommit`, `debug`, `apilookup`, `challenge`
ปิดโดยดีฟอลต์: `analyze`, `refactor`, `testgen`, `secaudit`, `docgen`, `tracer`

เปิดเพิ่มโดยลบชื่อออกจาก `DISABLED_TOOLS` ใน `.env` หรือ MCP settings:
```bash
# ดีฟอลต์
DISABLED_TOOLS=analyze,refactor,testgen,secaudit,docgen,tracer
# เปิดทั้งหมด
DISABLED_TOOLS=
```
หมายเหตุ: `version`, `listmodels` ปิดไม่ได้ · เปลี่ยนแล้ว restart session · แต่ละ tool กิน context ให้เปิดเท่าที่ใช้

</details>

## 📺 ดูเครื่องมือทำงานจริง

<details>
<summary><b>Chat Tool</b> — ตัดสินใจร่วมกัน + คุยหลายรอบ</summary>

[Chat Redis or Memcached_web.webm](https://github.com/user-attachments/assets/41076cfe-dd49-4dfc-82f5-d7461b34705d)
[Chat With Gemini_web.webm](https://github.com/user-attachments/assets/37bd57ca-e8a6-42f7-b5fb-11de271e95db)
</details>

<details>
<summary><b>Consensus Tool</b> — ดีเบตหลายโมเดล</summary>

[OpenClink Consensus Debate](https://github.com/user-attachments/assets/76a23dd5-887a-4382-9cf0-642f5cf6219e)
</details>

<details>
<summary><b>PreCommit Tool</b> — ตรวจการเปลี่ยนแปลงครบถ้วน</summary>

<div align="center"><img src="https://github.com/user-attachments/assets/584adfa6-d252-49b4-b5b0-0cd6e97fb2c6" width="950"></div>
</details>

## คุณสมบัติเด่น

**AI Orchestration** — เลือกโมเดลอัตโนมัติ · เวิร์กโฟลว์หลายโมเดล · บริบทต่อเนื่อง · [Context revival](docs/context-revival.md)
**รองรับโมเดล** — หลายผู้ให้บริการ (Gemini, OpenAI, Azure, X.AI, OpenRouter, DIAL, Ollama) · โมเดลล่าสุด · [Thinking modes](docs/advanced-usage.md#thinking-modes) · Vision
**ประสบการณ์นักพัฒนา** — เวิร์กโฟลว์แบบมีไกด์ · จัดการไฟล์อัจฉริยะ · web search · [รองรับพรอมป์ตใหญ่](docs/advanced-usage.md#working-with-large-prompts)

## Quick Links

**📖 เอกสาร:** [ภาพรวม](docs/index.md) · [Getting Started](docs/getting-started.md) · [Tools](docs/tools/) · [Advanced Usage](docs/advanced-usage.md) · [Configuration](docs/configuration.md) · [Adding Providers](docs/adding_providers.md) · [Model Ranking](docs/model_ranking.md)
**🔧 Fork:** [CHANGES-FORK.md](CHANGES-FORK.md) · [คู่มือ clink model/effort](docs/clink-model-effort-guide.md)
**🛠 Setup:** [WSL](docs/wsl-setup.md) · [Troubleshooting](docs/troubleshooting.md) · [Contributing](docs/contributions.md)

## License

Apache 2.0 — ดู [LICENSE](LICENSE)

## กิตติกรรมประกาศ

สร้างด้วยพลัง **Multi-Model AI** 🤝 — [MCP](https://modelcontextprotocol.com) · [Codex CLI](https://developers.openai.com/codex/cli) · [Claude Code](https://claude.ai/code) · [Gemini](https://ai.google.dev/) · [OpenAI](https://openai.com/) · [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/)

fork ดูแลโดย [xenodeve](https://github.com/xenodeve) — ต้นทาง [BeehiveInnovations/pal-mcp-server](https://github.com/BeehiveInnovations/pal-mcp-server)
