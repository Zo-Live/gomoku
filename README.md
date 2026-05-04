# 五子棋

本项目为一个简易的五子棋程序，使用 Python 编写，界面采用标准库 `curses`。

## 运行方式

```bash
python3 -m gomoku
```

或：

```bash
python3 main.py
```

运行环境要求：

- Python 3.11 及以上
- 支持 UTF-8 的终端
- 支持 `ncurses` 鼠标事件
- 终端窗口建议至少为 `92x28`

## 操作方式

### 主菜单

- 鼠标点击 `P1`：切换 `Human` / `Baseline`
- 鼠标点击 `Size`：切换棋盘大小 `9..19`
- 鼠标点击 `Start`、`Export`、`Quit`
- 键盘快捷键：`P`、`S`、`Enter`、`Q`

### 对局界面

- 方向键移动当前高亮格
- `Enter` 在当前格落子
- 鼠标点击一次切换选中格，再次点击同一格确认落子
- `M` 返回主菜单，并丢弃当前未结束对局
- `Q` 退出程序

## 功能说明

- 支持完整五子棋对局流程
- 支持自定义奇数棋盘尺寸：`9, 11, 13, 15, 17, 19`
- 黑棋固定先手
- 支持边界检测、重复落子检测、连五判定和平局判定
- 支持人机对战与 AI 对 AI
- 内置 baseline AI
- 支持对局保存与批量导出

## 数据导出

已结束对局会保存到：

```text
data/games/*.json
```

主菜单中的 `Export` 会生成：

- `exports/games.jsonl`
- `exports/moves.csv`

## 测试

```bash
python3 -m unittest discover -s tests -v
```
