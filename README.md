# 澄砾材料试验室双台架复盘

白班记录员录入测次动作和现场见证。班组复盘员核对指定修订的公开脚本并发行站件。夜班在两个站源关闭后签发双台复验资格，再按正式号领取原据与结果。

## 一天的操作

1. 分别打开站库与报告库。站库初始化时提供该作业的固定公开命令目录。
2. 台架记录员提交开场状态、全量动作原行和合格见证原行，得到固定修订键。
3. 发现误录时，以同作业同站的旧版为父提交完整勘误。父版仍按原号可读。
4. 复盘员对指定版复查公开脚本，核对是否可执行以及所走路径上的本站见证。
5. 班组冻结指定修订并交出 V1 站件。站内原行、状态编号、私有动作名称和原测说明留站。
6. 夜班关站源后按预期作业和站身份验收两个站件。
7. 按提交顺序绑定双父件并提交本次许可。中心签发可用首命令及发布记录。空资格也是正式结果。
8. 勘误和再次签发后，夜班按旧报告号领回旧结果、许可、双父件及回执。

## 共用面板复验（V2）

夜班只看共用面板的亮灭。`evidence.freeze.freeze_panel(store, key, lit_action_ids)` 按指定修订和本轮精确灯位声明冻结 V2 站件；同一修订同声明重发返回首件原文，改灯位须另做勘误修订。`evidence.acceptance.accept_panel(raw, expected_job, expected_station)` 验收 V2 件。`reports.publish.issue_panel(store, left, right, permissions, max_steps)` 签发带可执行策略树的正式报告，`reports.retrieve.read_panel(store, number)` 按号领取。详见 `PANEL.md`。

## Python 3.11 API

在项目根目录运行。工程只使用标准库。站库 `records.storage.RevisionStore(path)` 和报告库 `reports.storage.ReportStore(path)` 都支持 `with` 关闭及重开。站库使用 `initialize((catalog, ...))` 登记作业目录，报告库使用 `initialize()`。重复初始化保留已有修订、站件、报告和发布记录。同作业重复登记同一目录合法，改动固定目录会拒绝。样例由演示入口在新临时库中录入。

| 入口 | 参数与结果 |
| --- | --- |
| `records.intake.accept_revision` | `store, StationKey(job, station), RevisionDraft(opening, actions, witnesses), parent=None`，返回 `RevisionKey`。`parent` 是关键字参数，引用同作业同站固定版。 |
| `records.revisions.read_revision` | `store, key`，按明确修订键读取完整原行、目录和父版。未知键抛出 `RevisionMissing`。 |
| `review.script_check.review_script` | `store, key, commands`，接收有序命令序列，返回 `ScriptReview`。合法脚本无路可走时 `executable` 为假。目录外命令抛出 `UnknownCommand`。 |
| `evidence.freeze.freeze_station` | `store, key`，登记指定修订并返回 V1 JSON 文本。重复冻结取回原件。未知或不适用版抛出 `FreezeRejected`。 |
| `evidence.freeze.freeze_panel` | `store, key, lit_action_ids`，按精确修订冻结 V2 共用面板站件。`lit_action_ids` 为该修订一条或多条公开动作原行标识的非字符串集合。同声明重发取回首件原文，同修订改声明抛出 `FreezeRejected`。 |
| `evidence.acceptance.accept_station` | `raw, expected_job, expected_station`，返回保留正文、身份及原文本的 `AcceptedStation`。错件或坏件抛出 `StationAcceptanceError`。 |
| `evidence.acceptance.accept_panel` | `raw, expected_job, expected_station`，返回 `AcceptedPanel`。V1 件、坏件、错作业或错站抛出 `StationAcceptanceError`。 |
| `reports.publish.issue_report` | `store, left, right, permissions`，接收有序两份验收件和许可集合，返回 `ReportSnapshot`。拒绝或发布失败抛出 `ReportIssueError`。 |
| `reports.publish.issue_panel` | `store, left, right, permissions, max_steps`，绑定同作业异站、目录一致的两份 V2 验收件，签发 `PanelSnapshot`（含 `status` 与 `strategy`）。`max_steps` 为 0 至 8 的整数。 |
| `reports.retrieve.read_report` | `store, number`，返回已发布快照或 `MissingReport(number)`。 |
| `reports.retrieve.read_panel` | `store, number`，返回已签面板快照或 `MissingReport(number)`。 |

`review.commands.CommandCatalog(job, commands)` 固定一个作业的公开命令标识。`records.readings.ActionRow(row_id, source, target, kind, label, reading='')` 的 `kind` 为 `public` 或 `local`。`public` 行的 `label` 必须在目录中，`local` 行的 `label` 是本站动作名称。状态来自开场和动作两端。`WitnessRow(row_id, action_id, note='')` 只登记现场已判为合格的见证，必须指向本次修订的动作。两类行各自要求行号唯一。错误草稿或不适用的父版以 `RevisionRejected` 整版拒绝。标识按字符串精确比较，动作、命令出现和见证按实际经过的边计，无时间或浮点舍入假设。

单台复查允许有限站内动作，所走路径的公开投影须恰好等于所给脚本。空脚本允许在开场停止。只要存在经过合格见证的完整路径，复查优先返回这样的路径。候选按最少动作与动作行号顺序稳定选择，路径和见证只供本站复查。

## 交接与核定

V1 外层字段为 `version`、`job`、`station`、`revision`、`digest`、`body`。摘要绑定版本、身份和规范化正文，用于完整性核对。正文包含完整目录、匿名开场、局部状态范围和带见证布尔值的接续。公开步带命令，站内步标明类型。验收和报告均可在站库关闭后运行。

成对请求须绑定同作业不同站的两份固定件，且目录一致。许可是该目录的子集。目录内命令在某台没有实际路线时仍可提交，目录外命令使整项请求拒绝。中心允许两台各自执行有限次站内动作，两台只在获许可的同名公开命令上共同推进。首次公开命令前也可进行站内推进。某个真正的首命令之后，若存在同一条共同执行能无限次发生公开命令且两台各自无限次取得合格见证，该命令才列入。两台见证允许错开。`first_commands` 是升序元组，转为 JSON 后是数组。

SQLite 在一次事务中发布报告、按位置保存的父件和发布记录。错误请求及提交失败没有新增记录。历史领取按报告号读取原结果和原件，不需要重新核定。报告号及修订号在各自档案内分配，和所属作业、站及原文本一同标识出处。

## 核验与演示

```text
python3 -B check_project.py
python3 -B demo.py
```

`check_project.py` 由物化运行时提供，运行 `tests` 中完整回归，并额外用公开入口核验面板样例、同声明重发、拒办边界与签存失败后可重办。`demo.py` 实际关站后办理原乙件和勘误乙件，展示同一灯史的两个末步，重开报告库按原号分别领取，并保留原 V1 演示。
