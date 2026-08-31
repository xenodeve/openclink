# Invariants — สิ่งที่ระบบสัญญา เทียบกับจุดที่มันถูกบังคับจริง

อ่านหน้านี้ก่อนพึ่งพากฎข้อไหนก็ตามที่ข้ามขอบเขต — ไฟล์ สถานะ โมเดล งบ token หรือที่เก็บบทสนทนา

**แบบแผนที่ต้องจำ** — codebase นี้ประกาศกฎของตัวเองไว้ใน **docstring ของโมดูล** แล้วบังคับมันที่ **จุดเรียกเดียว** · ทางเข้าที่สองสู่ความสามารถเดียวกัน (การเขียนแทนการอ่าน · workflow tool แทน simple tool) จึงหลุดออกไปเงียบๆ เสมอ

*ตรวจเมื่อ 2026-08-13 ที่ `2aa6e49`*

## 1. ตารางกฎ

| กฎ | ประกาศที่ | บังคับที่ | ละเมิดที่ | คำตัดสิน |
|---|---|---|---|---|
| การเข้าถึงไฟล์จำกัดอยู่ใน PROJECT_ROOT | `utils/file_utils.py:16` | **ไม่มีที่ไหนเลย** · `resolve_and_validate_path:282` ตรวจแค่ absolute, resolve symlink, บล็อกไดเรกทอรีระบบ และ home root | ทุกการอ่าน · `tests/test_path_traversal_security.py:13-14` บันทึกไว้เองว่า `/home/user/project` **อนุญาตโดยตั้งใจ** | **ประกาศไว้ ไม่มีการบังคับ** ให้ถือว่าอ่านได้ทุกที่ในเครื่องยกเว้นบัญชีดำ |
| path ต้องเป็น absolute และถูกตรวจก่อนอ่าน | `file_utils.py:17` · `base_models.py:43` | สามตัวตรวจอิสระ + `resolve_and_validate_path` ใน `read_file_content:443` | **รูปภาพเลี่ยงทั้งหมด** — `images` ไม่อยู่ในรายการฟิลด์ที่ `base_tool.py:669-679` และ `image_utils.py:70` เปิดไฟล์ด้วย `open()` เปล่าๆ · **การเขียนก็เลี่ยง** — `chat.py:336-352` เขียนไฟล์ลงไดเรกทอรีที่ผู้เรียกระบุ ตรวจแค่ `isabs` + `isdir` | **บังคับเฉพาะเส้นทางอ่านข้อความ** |
| tool เป็น singleton และไร้สถานะ | `server.py:260` | ครึ่งแรกจริง — หนึ่ง instance ต่อ tool · **ครึ่งหลังไม่มีอะไรบังคับ** | เขียนลง `self` เต็มไปหมด — `_current_arguments`, `_model_context`, `work_history`, `consolidated_findings`, `_active_system_prompt` · MCP SDK ส่งแต่ละ request ด้วย `tg.start_soon` สอง call ที่ค้างอยู่จึงใช้ object เดียวกัน | **จริงครึ่งเดียว และครึ่งที่เท็จคือครึ่งที่อันตราย** |
| ทุกคำตอบที่ถึง host เป็น `ToolOutput` | `tools/models.py:29-46` | simple tool เท่านั้น | workflow tool ไม่เคยสร้าง `ToolOutput` สำหรับกรณีสำเร็จ — `workflow_mixin.py:736` คืน `json.dumps` ของ dict ธรรมดา · สถานะนอก `Literal` ถูกปล่อยเป็นประจำ เช่น `pause_for_<tool>`, `calling_expert_analysis`, `web_lookup_needed`, `challenge_accepted` | **`Literal` อธิบายตระกูลเดียวจากสองตระกูล** เพิ่มสถานะเข้าไปไม่ได้บังคับอะไร |
| โมเดลที่ระบุมาต้องเป็นโมเดลที่ provider ได้รับอนุญาตให้เสิร์ฟ | `model_restrictions.py:34-48` | ตรวจที่ขอบ `server.py:824-842` แล้วตรวจซ้ำต่อ call ที่ `openai_compatible.py:524` | tool ที่ `requires_model()` เป็น `False` ข้ามขอบทั้งหมด (`server.py:807-810`) · **`clink` ส่ง `request.model` เข้า process ตรงๆ ที่ `clink.py:330`** | **บังคับกับ call ที่ผ่าน provider · ไม่มีผลกับ clink** — `*_ALLOWED_MODELS` ไม่คุมสิ่งที่ clink spawn |
| turn ถูกบันทึกครั้งเดียวต่อการโต้ตอบ | `conversation_memory.py:86-89` | `server.py:1088` เขียน user turn | **ตัวเขียนที่สองที่ `simple/base.py:353` ไม่เคยถูกข้าม** — ดูข้อ 2 | **ไม่ถูกรักษา** |
| งบ token ที่ยื่นให้ tool คืองบที่มันใช้จริง | `model_context.py:99-117` | เลขคณิตใน `read_files:559-604` ถูกต้อง | รั่วสามทาง — history ถูกจัดงบด้วย `len//3` แต่รายงานด้วย `len//4` · `_force_embed_files_for_expert_analysis` ไม่สน `_remaining_tokens` · การตรวจขนาดที่ขอบเรียกเฉพาะ `absolute_file_paths` ซึ่ง workflow tool ไม่มี | **เลขคณิตถูก input ผิด** |
| clink เป็น read-only ตาม annotation | `clink.py:156-157` | **ไม่มีอะไรเลย** · `base_tool.py:205-213` เขียนเองว่า annotation เป็นแค่คำใบ้ "ไม่ใช่เรื่องความปลอดภัย" | config ที่ ship มาปล่อยสิทธิ์เขียนทั้งหมด — `gemini.json:5` `--yolo` · `codex.json:6` `--dangerously-bypass-approvals-and-sandbox` · `claude.json:5-6` `--permission-mode acceptEdits` | **ประกาศไว้ ไม่บังคับ และ config ที่ ship ขัดกับมัน** |

## 2. คำแก้ — guard ของบทสนทนาไม่เคยทำงาน

ระหว่างทำเอกสารนี้ agent ตัวหนึ่งรายงานว่าตัวเขียน turn ที่สองถูกข้ามไป เพราะ `server.py:1229` ใส่สตริง `=== CONVERSATION HISTORY ===` ลงใน prompt · **ตรวจด้วยการรันแล้วพบว่าไม่จริง**

`server.py:1229` ใส่ `conversation_history` ซึ่งมีหัวเปิด `=== CONVERSATION HISTORY (CONTINUATION) ===` (`conversation_memory.py:798`) และหัวปิด `=== END CONVERSATION HISTORY ===` (`:1000`) · **ไม่มีอันไหนมีสตริงที่ guard ที่ `simple/base.py:335` มองหาอยู่ข้างใน** · ตัวเขียนทั้งสองจึงทำงานทั้งคู่ และบทสนทนาโตเป็นเท่าตัวทุกเทิร์น

บันทึกไว้ตรงนี้เพราะมันเป็นตัวอย่างของสิ่งที่เอกสารชุดนี้มีไว้ป้องกัน — **ข้ออ้างที่มีหลักฐานอ้างอิงครบ ฟังขึ้น และผิด** ในข้อที่สำคัญที่สุดข้อเดียวพอดี

## 3. ลำดับที่สัญญาเรื่องไฟล์พังจริง

**ไฟล์ข้อความ** — เจ็ดทอด มีประตูจริงประตูเดียว และอยู่ท้ายสุด

```
handle_call_tool → _validate_file_paths (absolute เท่านั้น) → check_total_file_size
  → _prepare_file_content_for_prompt → read_files → read_file_content
  → resolve_and_validate_path     ← ประตูจริงประตูเดียว
```

**รูปภาพ** — `resolve_and_validate_path` ไม่อยู่ในสายนี้เลย

```
handle_call_tool → _validate_image_limits (นับจำนวนกับ MB) → provider.generate_content
  → validate_image → open()
```

**การเขียน** — ก็ไม่อยู่ในสายเช่นกัน

```
ChatTool.format_response → _persist_generated_code_block → write_text
```

**ถ้าคุณกำลังเพิ่มความสามารถที่แตะไฟล์ ให้ต่อเข้ากับ `resolve_and_validate_path` เอง** — การสืบทอดจาก `BaseTool` ไม่ได้ทำให้คุณ

## 4. สองข้อที่ถูกรักษาไว้จริง — รูปแบบที่ควรลอก

`clink` **ปฏิเสธเมื่อไม่ระบุ model** แทนที่จะถอยไปใช้ค่าเริ่มต้นของ client — ประกาศไว้ที่ `clink.py:110-115` และบังคับที่ `:280-286` ก่อนสร้าง agent · และ **ปฏิเสธ `images` ดังๆ** แทนที่จะเงียบๆ ทิ้ง (`:295-302`)

ทั้งสองข้อบังคับที่ **ต้นของ `execute` ก่อนงานที่แพง** และพกเหตุผลมาในบรรทัดเดียวกัน · นั่นคือทรงที่ควรลอก

## 5. สรุปสำหรับ agent — อะไรเชื่อได้ อะไรต้องตรวจเอง

**เชื่อได้** — registry ของ tool มี instance เดียวต่อ tool จริง · การบังคับข้อจำกัดโมเดลสำหรับอะไรก็ตามที่ไปถึง `ModelProvider` · ความเป็น absolute ของ path ไฟล์ข้อความในฟิลด์ที่ระบุไว้ที่ `base_tool.py:669-679` · และเลขคณิตภายในของ `read_files`

**ต้องตรวจเอง** — อย่าคิดว่า path อยู่ในโปรเจกต์ เพราะไม่มีขอบเขตโปรเจกต์ · อย่าคิดว่าคำตอบเป็น `ToolOutput` ต้องรับสองรูปแบบ · อย่าคิดว่า instance ของ tool ปลอดภัยเมื่อรันพร้อมกัน — ถ้าคุณเพิ่ม `self.<field> = …` ในเส้นทาง execute คุณกำลังขยายการแข่งกันที่มีอยู่แล้ว และทางแก้คือ object ต่อ request ไม่ใช่ lock · อย่าคิดว่า `_remaining_tokens` เป็นเพดานจริง · และ **อย่าคิดว่า `readOnlyHint` มีความหมาย** — สำหรับ clink มันเป็นเท็จใน config ที่ ship มา และไม่มีเทสต์ไหนจะสังเกตถ้าคุณเปลี่ยนมัน
