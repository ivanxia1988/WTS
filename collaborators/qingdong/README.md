# qingdong 协作区

这个目录专门用于 qingdong 提交已完成的 WTS Skill 源码和改动说明。

## 提交方式

1. 将完整的 Skill 文件包放入 `source/`（猎聘寻访 `wts`）或 `source-local/`（本地简历库寻访 `wts-local`）。
2. 在 `CHANGELOG.md` 顶部增加本次改动，说明改了什么、为什么修改、需要重点测试什么。
3. 提交并推送到 Git 后，通知维护者进行合并评审。

不要直接修改 `WTS/source/` 或 `WTS/versions/`。
