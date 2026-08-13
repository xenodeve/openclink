# PAL MCP Documentation Index

> [!important] นี่คือ **พิมพ์เขียวของโครงสร้าง** ไม่ใช่รายการข้อบกพร่อง และไม่ใช่ที่เก็บการตัดสินใจ
> เอกสารชุดนี้ตอบว่า **ระบบประกอบขึ้นมายังไง** เพื่อให้คนที่กำลังจะแก้อะไรสักอย่างมองเห็นรัศมีผลกระทบก่อนลงมือ
> · อะไรพัง → [`docs/reports/`](../docs/reports/) · ตัดสินใจอะไรไว้และทำไม → [`docs/adr/`](../docs/adr/) · งานที่ค้าง → [`docs/OPEN-WORK-LEDGER.md`](../docs/OPEN-WORK-LEDGER.md)

เอกสารชุดนี้มีอยู่เพราะปัญหาเดียว — **ที่ผ่านมาเราวิจัยทีละส่วนแล้วแก้ทีละส่วน โดยไม่เคยมีแผนผังของทั้งระบบ** ทำให้ทุกการแก้เป็นการให้เหตุผลจากข้อมูลบางส่วน ซึ่งเป็นกลไกที่ผลิต tech debt โดยตรง

## หลักที่แบ่งเอกสารชุดนี้เป็นสองครึ่ง

| ครึ่ง | ไฟล์ | เชื่อได้แค่ไหน |
|---|---|---|
| **สร้างจากโค้ด** | [GENERATED_STRUCTURE.md](GENERATED_STRUCTURE.md) | **เชื่อได้เสมอ** — สร้างใหม่ด้วย `python scripts/blueprint.py` ทุก checkpoint · ถ้าขัดกับเอกสารอื่น ให้เชื่อไฟล์นี้ |
| **เขียนมือ** | ที่เหลือทั้งหมด | เชื่อได้เท่าที่วันที่กำกับไว้ · แบกวิจารณญาณ จึงเน่าได้ |

การแยกแบบนี้ตั้งใจ · repo นี้เคยพิสูจน์แล้วว่าการแก้โค้ดหนึ่งครั้งทำให้เอกสารห้าฉบับผิดพร้อมกันโดยไม่มีใครแก้ — ครึ่งที่สร้างเองจึงถูกทำให้เป็นครึ่งที่ใหญ่กว่าเท่าที่จะทำได้

## System Documentation

1. [SYSTEM_ARCHITECTURE_OVERVIEW.md](SYSTEM_ARCHITECTURE_OVERVIEW.md) — ภาพรวมทั้งระบบ ชั้น ความรับผิดชอบ และ seam ที่ไม่ได้อยู่ตรงที่มันดูเหมือนจะอยู่
2. [GENERATED_STRUCTURE.md](GENERATED_STRUCTURE.md) — โครงสร้างที่วัดจากโค้ดจริง: กราฟ import, การข้ามชั้น, ฮับ, โมดูลที่ไม่มีเทสต์แตะ

## Subsystem Documentation

1. [Server/SERVER_OVERVIEW_AND_INTEGRATION.md](Server/SERVER_OVERVIEW_AND_INTEGRATION.md) — ขอบเขต MCP, วงจรชีวิตของคำขอทั้งสามแบบ, และรายการทางลัดที่ข้ามขั้นตอน
2. [Tools/TOOLS_OVERVIEW_AND_INTEGRATION.md](Tools/TOOLS_OVERVIEW_AND_INTEGRATION.md) — สองทรงของ tool, สัญญาที่ประกาศต่อ host, และจุดเสียบ tool ใหม่
3. [Clink/CLINK_OVERVIEW_AND_INTEGRATION.md](Clink/CLINK_OVERVIEW_AND_INTEGRATION.md) — การมอบงานให้ CLI ค่ายอื่น และจุดเสียบ client ใหม่
4. [Providers/PROVIDERS_OVERVIEW_AND_INTEGRATION.md](Providers/PROVIDERS_OVERVIEW_AND_INTEGRATION.md) — การแปลงชื่อโมเดลเป็นปลายทาง capability manifest และจุดเสียบ provider ใหม่
5. [Memory/MEMORY_OVERVIEW_AND_INTEGRATION.md](Memory/MEMORY_OVERVIEW_AND_INTEGRATION.md) — thread ของบทสนทนา งบ token และโครงสร้างข้อมูลที่ข้ามขอบเขต

## Cross-cutting

1. [INVARIANTS.md](INVARIANTS.md) — สิ่งที่ระบบสัญญาไว้ เทียบกับจุดที่มันถูกบังคับจริง · **อ่านก่อนพึ่งพากฎข้อไหนก็ตาม**
2. [BLAST_RADIUS.md](BLAST_RADIUS.md) — การแก้แต่ละข้อในลำดับความสำคัญกระเทือนถึงไฟล์ไหนบ้าง และอะไรต้องลงก่อนอะไร

## เส้นทางการอ่านที่แนะนำ

**ถ้ากำลังจะแก้อะไรสักอย่าง** — [GENERATED_STRUCTURE.md](GENERATED_STRUCTURE.md) เพื่อดูว่าโมดูลนั้นมีใครพึ่งพาบ้าง → [INVARIANTS.md](INVARIANTS.md) เพื่อดูว่ากฎข้อไหนที่คุณกำลังจะพึ่งนั้นถูกบังคับจริงไหม → [BLAST_RADIUS.md](BLAST_RADIUS.md) ถ้าสิ่งที่จะแก้อยู่ในรายการนั้นแล้ว

**ถ้ากำลังจะเพิ่มของใหม่** — เอกสารรายส่วนของชั้นนั้น หัวข้อ *จุดเสียบ* ซึ่งไล่ไฟล์ตามลำดับที่ต้องแตะ พร้อมระบุ **กับดัก** ที่คนทำตามตัวอย่างเดิมจะพลาด

**ถ้าเพิ่งเข้ามาใหม่** — [SYSTEM_ARCHITECTURE_OVERVIEW.md](SYSTEM_ARCHITECTURE_OVERVIEW.md) ทั้งฉบับ แล้วค่อยเลือกชั้นที่งานของคุณแตะ

## หน้าที่ของแต่ละโฟลเดอร์

* [Server](Server) — ขอบเขต MCP และวงจรชีวิตของคำขอ
* [Tools](Tools) — ชั้นที่ใหญ่ที่สุด และเป็นที่อยู่ของสัญญาที่ประกาศต่อ host
* [Clink](Clink) — การมอบงานให้ agent ค่ายอื่น ซึ่งเป็นสิ่งที่ fork นี้เพิ่มเข้ามา
* [Providers](Providers) — การเชื่อมกับ vendor ของโมเดล
* [Memory](Memory) — thread บทสนทนาและงบ token
