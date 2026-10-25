# 项目迁移记录：C 盘 → D 盘

日期：2026-09-16。

## 当前入口

- 项目主目录：`D:\Projects\549 native ads`。
- Dashboard：[本机实例](http://127.0.0.1:8050/)。
- 旧目录 `C:\Users\yaobc\Documents\ChatGPT\549 native ads` 已改为指向主目录的 Windows Junction。旧文档链接和当前工作区路径继续可用。
- 源码、Git、原始资料、数据库、备份和主虚拟环境均位于 D 盘。项目外共享的 Codex Python、Node 运行时仍在原安装位置。

## 验证结果

1. 停止应用和 PostgreSQL 后创建数据库备份，再复制文件；复制时不遍历外部运行时链接。
2. 复制完成时，60,298 个文件、4,616,830,105 字节的大小和 SHA-256 全部匹配；目录及链接目标也匹配。
3. 更新数据库目录标记，在 D 盘按照原 `uv.lock` 离线重建 `.venv`。主 Python、应用模块和 PostgreSQL 数据目录均确认解析到 D 盘。
4. 数据库迁移前后所有业务表内容、结构、序列和使用账本一致。数据版本：`5114ebc1cf9afe59cdaa715e3ea45166`。共 275 条活动记录、263 条可统计记录、226 条可检索记录和 558 个当前文本块。
5. 检查 110 个历史回答、704 个证据条目、177 个引用，原文定位无失败。此校验在页面试用前进行；它不评价回答的语义正确性。
6. 首页、Dash 布局、CSS 和来源链接脚本均返回 HTTP 200。页面实际验证 CNBC 筛选得到 116 条记录、103 条可检索记录；还原全库后，免费检索 `biogas` 返回 3 个证据片段。本次迁移没有调用付费模型。
7. 主项目 Git HEAD 保持 `62ff83d`，应用版本保持 0.2.5；源码没有因迁移修改。

## 清理状态：尚未完成

以下临时副本仍存在，尚未声称释放其占用空间：

- `C:\Users\yaobc\Documents\ChatGPT\549 native ads.migration-backup-20260916`
- `D:\Projects\549 native ads\.runtime\migration-20260916\previous-venv`

自动审批拒绝了永久删除，返回 `blocked by policy`。改用 Windows 回收站后，操作返回 `Attempted to perform an unauthorized operation`。因此保留副本，没有继续删除或改变系统权限。

清理前独立复核发现回退副本的 Git 文件多了一层 `.git/` 容器；将该唯一前缀差异规范化后，全部文件大小和 SHA-256 与迁移前清单相同，没有发现独有内容。D 盘主项目的 Git 目录结构正确。严格路径检查失败与内容等价检查通过分别保留，未混为一次成功校验。

完整私有校验记录位于 `D:\Projects\.observatory-migration-20260916`，包括复制、数据库、回退内容、HTTP 和最终状态记录。原始来源索引、历史报告和数据库来源路径保持原值，通过旧目录链接兼容。

## 技术参考

目录被当前工具进程占用，不能整体重命名；迁移使用已有空目录的 Junction 设置，未提升权限。实现依据 Microsoft 的 [FSCTL_SET_REPARSE_POINT](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_set_reparse_point) 和 [REPARSE_DATA_BUFFER](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_reparse_data_buffer) 文档。
