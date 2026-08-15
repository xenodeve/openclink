# Memory Overview and Integration

ชั้นความจำเก็บ thread ของบทสนทนา และเป็น **พื้นผิวการเก็บถาวรเพียงหนึ่งเดียวของทั้งระบบ** — ซึ่งไม่ถาวรเลย

*เขียนเมื่อ 2026-08-13 ที่ `2aa6e49`*

## 1. พื้นผิวการเก็บ

| | |
|---|---|
| ที่เก็บ | `InMemoryStorage._store: dict[str, tuple[str, float]]` — `utils/storage_backend.py:35` |
| key | `f"thread:{thread_id}"` |
| value | `ThreadContext.model_dump_json()` — **สตริง JSON ไม่ใช่ object** |
| อายุ | TTL แบบเลื่อน เลื่อนเฉพาะตอนเขียนสำเร็จ |

**ไม่มี Redis ไม่มี disk ไม่มีฐานข้อมูล** · `get_storage_backend()` คืน singleton ในหน่วยความจำแบบไม่มีทางเลือกอื่น · และเพราะ transport เป็น stdio ตัว server เป็น subprocess ของ client — **thread ตายพร้อม session ของ client ไม่ใช่แค่ตอน restart**

ทุกการอ่านและทุกการเขียน deserialize/serialize **ทั้ง thread** · `chat` continuation หนึ่งครั้งทำ `model_validate_json` เต็มก้อนราวเก้าครั้งและเขียนเต็มก้อนสองครั้ง — ต้นทุนเป็น O(turns) ต่อการกระทำ และ O(turns²) ต่อบทสนทนา

## 2. ใครเขียน `ConversationTurn` บ้าง และเขียนไม่เท่ากัน

| ผู้เขียน | role | ได้ `images` | ได้ `tool_name` |
|---|---|---|---|
| `server.py:1088` | user | **ไม่** | **ไม่** |
| `tools/simple/base.py:353` | user | **ไม่** | **ไม่** |
| `tools/simple/base.py:675` | user | ได้ | ได้ |
| `tools/simple/base.py:766` | assistant | — | ได้ |
| `tools/clink.py:473` | assistant | — | ได้ |
| `workflow_mixin.py:1125` | assistant | — | ได้ |

**สองตัวแรกเป็นตัวเขียน user turn ที่ทำงานทั้งคู่** — guard ที่ควรกันตัวที่สองไม่เคยตรงกัน ดู [INVARIANTS.md](../INVARIANTS.md) ข้อ 2 · ผลคือ **สาม turn ต่อการโต้ตอบหนึ่งครั้ง และ prompt โตเป็นเท่าตัวทุกรอบ**

และเพราะ turn ของ continuation ไม่พก `images` กับ `tool_name` **รูปที่แนบมาตั้งแต่เทิร์นที่สองเป็นต้นไปจะหายจาก thread** ทั้งที่ถูกส่งให้โมเดลไปแล้ว

## 3. `model_metadata` — ช่องเดียว สามสคีมา ไม่มีตัวอ่านกลาง

| ผู้เขียน | รูปร่าง |
|---|---|
| `tools/clink.py:482` | `{"accounting": {...}}` |
| `tools/simple/base.py` | `{"usage": ..., "metadata": ...}` |
| `workflow_mixin.py:1122-1133` | `{"work_history": [...], "initial_request": ...}` |

ฟิลด์ประกาศเป็น `Optional[dict[str, Any]]` ซึ่ง Pydantic ไม่ validate อะไรเลย · **ไม่มี discriminator ไม่มี union** · workflow tool ยืมช่องที่ชื่อว่า model metadata ไปเก็บสถานะของ workflow และ **เก็บ `work_history` ทั้งก้อนใหม่ทุก turn** ทั้งที่การกู้อ่านแค่ก้อนล่าสุด — เป็นการเปลืองที่โตตามกำลังสองของจำนวนขั้น

## 4. `tools/models.py` — 26 จาก 28 ชื่อไม่มีใครอ่าน

| ชื่อ | การอ้างอิงในโค้ดโปรดักชัน |
|---|---|
| `ToolModelCategory` | 95 |
| `ToolOutput` | 32 |
| `ContinuationOffer` | 6 |
| **อีก 26 คลาสที่เหลือ** | **0** |

และภายใน `ToolOutput` เอง — `status` เป็น `Literal` 13 ค่าแต่ **เอื้อมถึงจริงห้าค่า** · `content_type` เป็นสตริง `"text"` ที่ทุกจุดสร้าง ส่วน `"markdown"` กับ `"json"` ประกาศไว้แล้วไม่เคยถูกผลิต

**`tools.models` เป็นโมดูลที่ถูก import มากที่สุดในระบบ 27 ตัว** · ใครที่จะขยายซองคำตอบจะอ่านไฟล์นี้เป็นสัญญา แล้วต่อของใหม่เข้ากับ `SPECIAL_STATUS_MODELS` ซึ่งไม่มีโค้ดไหนบริโภค

## 5. งบ token

| ฟิลด์ของ `TokenAllocation` | ตัวอ่านในโปรดักชัน |
|---|---|
| `file_tokens` | 7 จุด |
| `total_tokens` / `content_tokens` | 4 จุด |
| `history_tokens` | **1 จุด** |
| `response_tokens` | **`logger.debug` จุดเดียว** — คำนวณทุก request ใช้ทำอะไรไม่ได้ |
| `available_for_prompt` | **ศูนย์** |

**ตัวประมาณ token สามตัวไม่ตรงกันในไปป์ไลน์เดียว** — `len//3` ตัดสินว่า turn ไหนเข้า history ได้ · `len//4` ผลิตตัวเลขที่ถูกรายงานและถูกลบออกจากงบไฟล์ · และประตูขนาดไฟล์ที่ขอบใช้ `bytes ÷ ratio` ที่ 2.5–4.5 · ไฟล์ `.json` จึงถูกให้คะแนนสูงกว่าโดยประตู 60% เทียบกับตัวที่บริโภคจริง

## 6. สิ่งที่ต้องรู้ก่อนแก้ชั้นนี้

**`add_turn` เป็น read-modify-write ที่ไม่มี lock ครอบทั้งคู่** — lock ของ storage ครอบ get กับ set แยกกัน สอง call ที่ทำงานพร้อมกันบน `continuation_id` เดียวจึงทำ turn หายเงียบๆ · นี่คือโครงสร้างที่แชร์กันจริงเพียงตัวเดียวบนเส้นทาง clink และมันไม่ถูกป้องกัน

**เพดาน `MAX_CONVERSATION_TURNS` คืนค่า `False` และทุกผู้เรียกเมินค่านั้น** — tool ยังตอบ turn หายเงียบๆ และ `remaining_turns` ที่โฆษณาให้ผู้เรียกนับเป็น turn แต่เรียกมันว่า exchange

**ข้อความ error ตอน thread หมดอายุเขียนตายว่า "more than 3 hours ago"** ไม่ว่าจะตั้งค่า `CONVERSATION_TIMEOUT_HOURS` ไว้เท่าไหร่

**การต่อบทสนทนาข้าม tool ตัดสินโดย tool ที่ *สร้าง* thread** ไม่ใช่ตัวที่กำลังถูกเรียก · การต่อ thread ของ clink ด้วย `chat` จึงไปแปลงโมเดลใหม่แทนที่จะสืบทอดโมเดลของ thread
