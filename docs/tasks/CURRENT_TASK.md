# CURRENT_TASK：T015 SIM 卡与 4G 数据链路验证

## 任务目标

确认插入手机 SIM 卡后，SIM7670G 是否能识别 SIM、注册蜂窝网络、附着分组数据，并完成最小公网连通性验证。

## 范围

- 枚举 SIM7670G USB 串口和 RNDIS 网卡；
- 查询 SIM 状态、信号、运营商、注册状态和分组数据附着状态；
- 必要时执行 SIM7670G 软重启，让热插入 SIM 后重新检测卡状态；
- 使用模块 AT TCP/IP 栈进行公网 ping 验证；
- 记录 Windows RNDIS 路径是否可直接上网。

## 不做

- 不拨打电话或发送短信；
- 不改写长期 APN 配置；
- 不刷写固件；
- 不把完整 ICCID/IMEI 写入状态文档。

## 允许修改路径

- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

- `python scripts/egolink_board_probe.py --skip-esp-log --probe-all-sim-ports`
- `AT+CPIN?`
- `AT+COPS?`
- `AT+CEREG?`
- `AT+CGATT?`
- `AT+CGDCONT?`
- `AT+NETOPEN`
- `AT+IPADDR`
- `AT+CPING="8.8.8.8",1,4,64,1000,10000,255`
- `ping -S 192.168.0.100 -n 4 8.8.8.8`

## 执行结果

- SIM7670G 在 `COM6` / `COM7` 均响应 AT 命令；
- 初次查询返回 `SIM not inserted`，执行 `AT+CFUN=1,1` 软重启后恢复；
- `AT+CPIN?` 返回 `+CPIN: READY`；
- `AT+COPS?` 返回 `460-00` LTE；
- `AT+CEREG?` 返回 `0,1`，表示 EPS/LTE 已注册；
- `AT+CGATT?` 返回 `1`，表示分组数据已附着；
- APN 为 `CMNET`，模块侧 IPv4 地址为 `10.36.158.99`；
- `AT+CPING` 到 `8.8.8.8` 4/4 成功；
- Windows RNDIS 网卡能获得 `192.168.0.100`，但指定该源地址 ping/curl 外网仍超时，RNDIS 直接上网路径后续单独处理。

## 完成标准

- SIM 卡识别成功；
- LTE 注册成功；
- 分组数据附着成功；
- 模块 AT TCP/IP 栈公网连通成功；
- RNDIS 限制已记录。
