# CA Prostate Interactive Dashboard

ไฟล์นี้เป็นแบบ standalone พร้อมข้อมูลจาก Excel แล้ว

## ใช้งาน
เปิด `index.html` ได้ทันที หรืออัปขึ้น GitHub Pages โดยวางไฟล์เหล่านี้ไว้ root ของ repo:

- index.html
- data.js (เก็บไว้เป็นข้อมูลสำรอง/สำหรับ regenerate)
- .nojekyll

## แปลง Excel ใหม่
```bash
pip install pandas xlrd
python convert_excel_to_datajs.py "รายงานสรุปข้อมูลผู้ป่วยมะเร็งต่อมลูกหมาก (CA Prostate) ปี 2564-2568.xls"
```
แล้วนำข้อมูลจาก data.js ไป regenerate dashboard หรือใช้ index.html รุ่น fetch data.js เดิม


## Update: Stage treatment pies
Dashboard version นี้เพิ่ม section “วิธีรักษาแยกตามระยะจาก T” เป็น pie chart 4 กราฟ ได้แก่ ระยะที่ 1-4 โดยแต่ละ pie แบ่งตามวิธีรักษา และไม่รวมกลุ่มไม่ระบุ T เพื่อให้แพทย์อ่านง่ายกว่า Stage → Treatment Flow.
