# Do truc tiep luong lenh dashboard -> Mininet -> dashboard

Muc tieu cua buoc nay la tra loi bang so: sau khi bam nut tat/bat link, he thong
cham o dau?

Co 2 thay doi ho tro do:

- `bridge/sync_agent.py` ghi them `STATE_DETECTED` khi collector thay state moi.
- `bridge/sync_agent.py` ghi them `STATE_PUSHED` khi patch state moi len Ditto thanh cong.
- `measurements/trace_latency.py` doc `logs/command_flow.log` va in bang latency tung chang.

## 1. Chay he thong

Neu vua sua code, phai restart `run_sync.py` de Sync Agent nap code moi.

Terminal 1: chay controller OpenFlow.

```bash
cd ~/dt4n
ryu-manager mininet.controller_static --ofp-tcp-listen-port 6653
```

Terminal 2: chay Mininet + Sync Agent + Command Agent.

```bash
cd ~/dt4n
sudo mn -c
sudo /usr/bin/python3 -m mininet.run_sync --period 1.0 --convergence-timeout 8
```

Terminal 3: chay dashboard.

```bash
cd dashboard
npm run dev
```

Mo dashboard tai `http://localhost:5173`.

## 2. Do bang dashboard that

Neu muon log moi gon hon, co the xoa noi dung file flow truoc khi demo:

```bash
: > logs/command_flow.log
```

Tren dashboard:

1. Bam vao mot link, vi du `h1-s1`.
2. Bam `Disable`.
3. Doi den khi mau link doi.
4. Bam `Enable`.
5. Doi den khi mau link doi.

Sau moi lan bam, chay:

```bash
/usr/bin/python3 measurements/trace_latency.py --limit 10
```

Hoac xem lien tuc:

```bash
watch -n 1 '/usr/bin/python3 measurements/trace_latency.py --limit 10'
```

Y nghia cac cot:

- `route`: tu luc UI ghi `CLICK` den luc Command Agent ghi `RECEIVE`.
- `lock`: thoi gian Command Agent cho `net_lock` sau khi da nhan lenh.
- `exec`: tu `RECEIVE` den `EXECUTE_DONE`; day la tong thoi gian cho lock + thao tac Mininet.
- `detect`: tu `EXECUTE_DONE` den `STATE_DETECTED`; day la thoi gian cho chu ky Sync Agent.
- `push`: tu `STATE_DETECTED` den `STATE_PUSHED`; day la thoi gian patch len Ditto.
- `ui`: tu `STATE_PUSHED` den `STATE_OK`; day la thoi gian Ditto SSE ve dashboard.
- `total`: tu `CLICK` den `STATE_OK`; day la cam giac nguoi dung nhin thay.

Cach ket luan nhanh:

- `route` lon, vi du > 3000 ms: duong lenh xuong Ditto/SSE/Command Agent cham.
- `lock` lon: Command Agent da nhan lenh nhung dang bi Sync Agent/Mininet giu `net_lock`.
- `exec` lon nhung `lock` nho: thao tac Mininet cham.
- `detect` xap xi `period`: binh thuong voi polling; muon nhanh hon thi giam `--period`.
- `push` lon: Ditto hoac mang local cham khi patch state.
- `ui` lon, hoac note `RESYNC`/`TIMEOUT`: dashboard khong nhan realtime SSE tot.
- note `Ditto response timeout`: bien nhan truc tiep het timeout, nhung lenh van co the thuc thi sau do.

Vi du tu log cu hien tai:

```text
target                 route   lock   exec  detect  push   ui    total  note
----------------------------------------------------------------------------------
link-s2-srv1             6396      0     18    --      --      --     9740  Ditto response timeout
link-s2-srv1             9151      0      4    --      --      --    10056  Ditto response timeout
```

Ket luan cua bang nay: thao tac Mininet rat nhanh (`exec` 4-18 ms), nhung lenh
di tu UI toi Command Agent mat 6-9 giay (`route`). Cac cot `detect/push/ui` dang
`--` vi log nay duoc tao truoc khi them trace Sync Agent; restart `run_sync.py`
roi bam lai se co so moi.

## 3. Do tu dong khong can dashboard

Tu dong dung mang, gui lenh disable/enable qua Ditto, in tung chang latency:

```bash
sudo /usr/bin/python3 -m mininet.run_sync --measure-flow --trials 3 --measure-link h1-s1 --period 1.0 --flow-reset-log
```

Ket qua duoc in ra terminal va ghi vao:

```bash
logs/command_flow_measure.log
```

Xem nhanh file report:

```bash
tail -120 logs/command_flow_measure.log
```

Muon doi ten file report:

```bash
sudo /usr/bin/python3 -m mininet.run_sync --measure-flow --trials 3 --measure-link h1-s1 --period 1.0 --flow-reset-log --flow-report logs/h1_s1_measure.log
```

Moi trial gom 2 lenh: `disableLink` roi `enableLink`. Bang ket qua co cac cot:

- `ack`: tu luc script gui POST den luc Ditto tra response message.
- `route`: tu luc script gui lenh den luc Command Agent nhan lenh.
- `lock`: thoi gian Command Agent cho `net_lock` sau khi da nhan lenh.
- `exec`: Command Agent nhan lenh -> Mininet thuc thi xong, gom ca thoi gian cho lock.
- `detect`: Mininet thuc thi xong -> Sync Agent phat hien state mong doi.
- `push`: Sync Agent phat hien -> patch Ditto xong.
- `ui`: patch Ditto xong -> twin state dat mong doi.
- `total`: tong tu luc gui lenh den khi twin state dung.

Neu `Baseline direct-up` van bao `twin=down` trong khi `runtime` hien interface
UP, collector dang doc sai state cua link.

Do mot link khac:

```bash
sudo /usr/bin/python3 -m mininet.run_sync --measure-flow --trials 3 --measure-link s2-srv1 --period 1.0 --flow-reset-log
```

Do rieng vong sync Mininet -> Ditto:

```bash
sudo /usr/bin/python3 -m mininet.run_sync --measure-latency --trials 10 --measure-link h1-s1 --period 1.0
```

Do vong command end-to-end qua Ditto message:

```bash
sudo /usr/bin/python3 -m mininet.run_sync --measure-command --trials 10 --measure-link h1-s1 --period 1.0
```

Hai script nay dung polling Ditto de xac nhan state, nen phu hop cho bao cao
so lieu lap lai. `trace_latency.py` phu hop de soi tung lan bam tren dashboard.
