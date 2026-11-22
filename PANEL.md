# 共用面板复验交班

两台架各有动作和现场合格见证。夜班每轮向两台发同一条公开命令，只能看到两台完成后的共用面板。任一台该动作亮灯，面板就亮。下一条命令和停检都以夜班办得到的观测为准。

## 站件与验收

- `evidence.freeze.freeze_panel(store, key, lit_action_ids) -> str` 读取指定 `RevisionKey`，返回 V2 站件 JSON 文本。`lit_action_ids` 是动作原行标识的非字符串可迭代对象，按集合认定。每个标识必须属于指定修订的一条公开动作。列入者亮灯，其余公开动作灭灯。空集合有效。同修订等价声明重发返回首件原文，改灯位须另用勘误修订。同修订声明冲突、未知修订或非法声明抛 `FreezeRejected`。
- `evidence.acceptance.accept_panel(raw, expected_job, expected_station)` 返回可交给签发入口的验收值，保有 `identity` 和原文本 `raw`。坏件、错作业、错站和 V1 件抛 `StationAcceptanceError`。原 V1 验收同样拒绝 V2。
- V2 外层用 `version`、`job`、`station`、`revision`、`digest`、`body`。沿用 V1 的 JSON 规范化和摘要口径，摘要输入的版本改为整数 `2`。验收核对外层及正文结构、类型、引用完整性和摘要，拒绝重复字段。正文编码可自定，须固定完整命令目录及匿名开场，保全每个匿名起点经有限站内准备接一条公开动作的全部可能落点、是否有本轮见证、该公开动作灯位的联合关系。动作原行标识、私有状态名、站内动作名和原测留站。

## 一轮与停检

开场时两台都站在各自件内的开场状态，均未取得见证。每轮从上次公开动作的落点开始。各台可执行零条或任意有限条站内动作，再完成所下命令的一条公开动作。所有能完成该命令的走法都是可能结果。若某个相容起点上任一台没有这样的走法，本轮不能选该命令。站内准备不另耗公开步数，也不单独产生观测。准备和公开动作上的合格见证均计入该走法，此前已取得的见证继续有效。

路径须符合此前所下命令和面板亮灭的完整历史。停检只发生在开场或一轮完成后，停检时每条相容路径均须已取得两台各自的见证。零步和空许可可以申报。

## 签发和领取

`reports.publish.issue_panel(store, left, right, permissions, max_steps)` 使用现有 `ReportStore`。左右必须是同作业异站且目录一致的两份 V2 验收件，依提交顺序绑定。核对验收值与原文。许可沿用 V1 的目录子集规则，规范成升序去重元组。`max_steps` 是 0 至 8 的整数，布尔值无效。非法请求、错件、混版和签存失败抛 `ReportIssueError`。

返回快照的属性为 `number`、`job`、`stations`、`parents`、`permissions`、`max_steps`、`status`、`strategy`、`receipt`。`stations` 和 `parents` 是左右顺序的二元组，父件保存原文本。回执沿用 `PublicationReceipt(number, 'issued')`。`status` 为 `impossible` 时 `strategy` 为 `None`，仍签发正式报告。`status` 为 `guaranteed` 时，`strategy` 是 JSON 兼容的树。停检叶为 `{"stop": true}`。下令节点形如 `{"command": "p", "next": {"0": ..., "1": ...}}`，其中 `0` 为灭、`1` 为亮，`next` 只列实际可能出现的面板值，值为子树。任意满足上限和取证要求的策略均可签发。

`reports.retrieve.read_panel(store, number)` 从档案读回已签快照，查无该号的面板报告时返回 `MissingReport(number)`。报告、规范请求、有序原件及回执同次入账。提交失败不新增成功记录，可用同一申请重办。关站、勘误和报告库重开之后均按号领取签发时的存值。原 V1 入口、件字节、历史报告和回归照常。

## 夜班工单样例

`panel_fixtures.py` 提供原动作、灯位及见证。`stage_sources(alpha_path, beta_path, freeze)` 以现有录入入口建两站并提交勘误，以传入的 `freeze(store, key, lit_action_ids)` 冻结，返回各样例的原文本。函数返回时两站都已关闭。可直接运行 `python3 -B panel_fixtures.py` 查看这些输入在 V1 的投影和核定结果。

对 `alpha`、`beta` 开放全部五个命令时，前两步是 `p`、`q`。`p` 分别把两台送到各自的 0 或 1 位，本站仅在走到 1 位时亮灯。两台完成 `q` 后才有末步，`q` 的灯只反映甲是否在 1 位。`r` 对应甲 0 乙 1，`s` 对应甲 0 乙 0，`t` 对应甲 1 且乙任意位。各合法末步均取得双台见证，灯灭即可停检。

原乙件的末步依次为 `s`、`r`、`t`，对应 `p` 灭且 `q` 灭、`p` 亮且 `q` 灭、`p` 亮且 `q` 亮。乙件勘误后依次为 `r`、`s`、`t`。两版各自三步可保证，两步均签 `impossible`。换用 `alpha_flat` 及原乙件时，`q` 在两位下都灭。同一个 p 亮且 q 灭的历史不能统一选出合法末步，三步签 `impossible`。用 `witness_left` 和 `witness_right` 只许 `p` 且限一步时，左台可先绕一条取证自环，也可直接做 `p`。两种走法均灭灯且落点相同，只前者有左证，应签 `impossible`。

## 验证交付

沿用现有 `.pointwise-runtime.json` 的命令数组约定。`verify` 运行完整原回归并通过公开入口核验面板样例、重发和拒办边界，以及签存失败后无新增且能重办，任一核验失败时非零退出。`demo` 实际关站后办理原乙件和勘误乙件，展示同一灯史的两个末步，并重开报告库按原号分别领取。原回归入口仍可单独运行。
