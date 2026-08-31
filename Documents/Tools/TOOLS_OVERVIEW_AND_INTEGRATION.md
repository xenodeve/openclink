# Tools Overview and Integration

ชั้น `tools/` คือ **ครึ่งหนึ่งของทั้งระบบ** — 31 โมดูล 15,740 บรรทัด · เป็นที่อยู่ของ business logic ทั้งหมด และของ **สัญญาที่ประกาศต่อ host** ผ่าน JSON Schema

*เขียนเมื่อ 2026-08-13 ที่ `2aa6e49`*

## 1. สองทรง และการเลือกทรงเปลี่ยนเกือบทุกอย่าง

| ทรง | ฐาน | ตัวอย่าง | คำตอบที่ส่งกลับ |
|---|---|---|---|
| **Simple** | `tools/simple/base.py:24` | `chat` `clink` `challenge` `apilookup` | `ToolOutput` serialize เป็น JSON |
| **Workflow** | `tools/workflow/base.py:24` + `workflow_mixin.py` | 12 ตัว รวม `debug` `codereview` `analyze` `planner` `consensus` | `json.dumps` ของ dict ธรรมดา — **ไม่ใช่ `ToolOutput`** |
| **BaseTool ตรงๆ** | `tools/shared/base_tool.py:46` | `listmodels` `version` | ประกอบเอง |

**ผลของความต่างข้อสุดท้ายคือไม่มีสัญญาคำตอบเดียว** · ถ้าคุณกำลังเขียนตัวอ่านผลลัพธ์ ต้องรับทั้งสองรูปแบบ และการเพิ่มสถานะเข้า `Literal` ที่ `tools/models.py:32` **ไม่ได้บังคับอะไรกับ workflow tool เลย** ดู [INVARIANTS.md](../INVARIANTS.md)

## 2. จุดเสียบ — เพิ่ม tool ใหม่

| # | ไฟล์ | เขียนอะไร |
|---|---|---|
| 1 | `tools/<name>.py` (ใหม่) | dict คำอธิบายฟิลด์ · request model · คลาสของ tool |
| 2 | `systemprompts/<name>_prompt.py` + `systemprompts/__init__.py:5-38` | ค่าคงที่ของ prompt และสองรายการ (import + `__all__`) |
| 3 | `tools/__init__.py:5-22` และ `:24-41` | import คลาส เพิ่มลง `__all__` |
| 4 | `server.py:49-67` | เพิ่มคลาสในบล็อก `from tools import (...)` |
| 5 | `server.py:261-280` | `"<name>": YourTool(),` ลง `TOOLS` — **บรรทัดนี้คือการลงทะเบียน** |
| 6 | `server.py:284+` `PROMPT_TEMPLATES` | ไม่บังคับ · ไม่ใส่ก็ตกกลับอย่างสวยงาม |
| 7 | `tests/test_<name>.py` | `pytest.ini` ตั้ง `testpaths = tests` ดังนั้น `simulator_tests/` ไม่ถูกรัน |

**เมธอดที่ต้องเขียนเอง** — `BaseTool` ประกาศ abstract หกตัว: `get_name` `get_description` `get_input_schema` `get_system_prompt` `get_request_model` `prepare_prompt` · `execute` เป็น concrete แต่โยน `NotImplementedError` ฐานที่คุณเลือกต้องเติมให้ · `SimpleTool` เพิ่ม `get_tool_fields` · `WorkflowTool` เพิ่มอีกสามตัวคือ `get_required_actions` `should_call_expert_analysis` `prepare_expert_analysis_context`

## 3. เครื่องสร้าง schema ที่ไม่มีใครเรียก

ทั้ง `SimpleTool` และ `WorkflowTool` มี `get_input_schema` ที่ใช้งานได้อยู่แล้ว · **แต่ tool ทั้ง 18 ตัวที่ ship มา override มันหมด และไม่มีตัวไหนเรียกของที่สืบทอดมาเลย**

workflow tool ทั้ง 12 ตัว import `WorkflowSchemaBuilder` เข้าไปใน override ของตัวเองแล้วเรียก `build_schema` เอง · simple tool ส่วนใหญ่เขียน dict ด้วยมือ · **นี่คือเหตุผลที่ `tools.workflow.schema_builders` มี 13 โมดูลพึ่งพาแต่ไม่มีเทสต์ไหนเอ่ยถึงเลย** — มันถูกเอื้อมถึงผ่าน 12 จุดเรียกอิสระ แต่ละจุดเลือก argument ของตัวเอง

**ผลกับคุณ** — `get_tool_fields()` เป็นน้ำหนักตายถ้าไม่เดินผ่าน implementation ของฐาน · `chat` ดูแลสี่ฟิลด์เดียวกันสองชุด และชุดที่สองมีแค่เทสต์เดียวที่อ่าน

## 4. `requires_model()` เปลี่ยนอะไรที่ขอบ

ค่าเริ่มต้นคือ `True` · คืน `False` แล้ว `server.py:807-810` จะลัดออกไปทันที และ **สามอย่างไม่เกิดขึ้น** — การแปลง auto mode เป็นโมเดลจริง · การตรวจว่ามี provider เสิร์ฟได้ไหม · และการกันขนาดไฟล์ที่ขอบ (ซึ่งอย่างไรก็ดูเฉพาะ `absolute_file_paths` ไม่เคยดู `relevant_files`)

`_model_context` และ `_resolved_model_name` ก็ไม่ถูกฉีดเข้า arguments · **workflow tool ที่ `requires_model()` เป็น `False` จึงต้องคืน `False` จาก `requires_expert_analysis()` ด้วย** ซึ่ง `planner` `tracer` `docgen` `consensus` ทำครบ

## 5. กับดัก

**`config.DEFAULT_MODEL` ค่าเริ่มต้นคือ `"auto"`** ดังนั้น `is_effective_auto_mode()` เป็นจริงบนเครื่องที่ติดตั้งมาตรฐาน และ `build_schema` ที่ได้รับ `auto_mode=True` จะเติม `"model"` เข้า `required`

`WorkflowTool.get_input_schema` กันเรื่องนี้ไว้ถูกต้อง — ส่ง `model_field_schema=None, auto_mode=False` เมื่อ `requires_model()` เป็นเท็จ · **การ override `get_input_schema` ทำให้การกันนั้นหายไป และ tool ที่ ship มาสองตัวหายไปแล้ว**

`PlannerTool` และ `TracerTool` คืน `False` จาก `requires_model()` แต่ override ของทั้งคู่ส่ง `model_field_schema=self.get_model_field_schema(), auto_mode=self.is_effective_auto_mode()` · **ทั้งคู่จึงประกาศว่า `model` เป็นพารามิเตอร์ที่ต้องมี สำหรับ tool ที่ทิ้งค่านั้นที่ `server.py:807`** · `consensus` กับ `docgen` ทำถูก — **ลอกสองตัวนั้น อย่าลอก planner หรือ tracer**

## 6. สิ่งที่ต้องรู้เพิ่มก่อนแก้ tool ที่มีอยู่

**tool ทุกตัวเป็น singleton และไม่ไร้สถานะ** · มี 11 ฟิลด์ที่รอดข้ามงานคนละชิ้น และ `consolidated_findings` เป็น input เดียวของ prompt ที่ส่งให้โมเดลภายนอก ดู [INVARIANTS.md](../INVARIANTS.md) ข้อ 1

**prompt ของ `planner` `tracer` `docgen` ไปไม่ถึงโมเดล** — 29,879 ไบต์ · `get_system_prompt()` ถูกอ่านเฉพาะใน `_call_expert_analysis` ซึ่งทั้งสามตัวปิดไว้ · **แก้ไฟล์ prompt ของสามตัวนี้ไม่มีผลอะไรเลย** พฤติกรรมของมันอยู่ในสตริง `next_steps` ในตัว tool

**สี่ตัวสร้าง prompt ด้วย `"\\n"` ที่เป็นแบ็กสแลชจริงแทน newline** — `analyze` `codereview` `precommit` `refactor` · `debug` กับ `secaudit` สะอาด ซึ่งเป็นสิ่งที่พิสูจน์ว่าเป็นความผิดพลาดไม่ใช่ธรรมเนียม ดู `docs/reports/2026-08-13-*` หัวข้อ 7
