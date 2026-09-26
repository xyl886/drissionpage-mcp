# -*- coding: utf-8 -*-
"""动作链工具：把 DrissionPage 的 ``Actions`` 暴露成一步可执行的动作序列。

为什么需要它
------------
真实采集里有一类操作**没法用单个 click/input 表达**：

- 滑块验证码：按下 → 分步平移（带时长）→ 松开；
- 组合键：Ctrl+A 全选、Shift+点击多选、Enter 提交；
- 画布/地图/图表：按坐标移动、拖拽、滚轮缩放；
- 按住拖动排序（HTML5 拖放之外的场景）。

这些都要按顺序、带状态地执行，``Actions`` 正是为此设计的。
本模块把「动作序列」做成一个工具：模型给出一串动作，按序执行。

对应 Python::

    page.actions.move_to(ele).hold().move(offset_x=300, duration=2).release()
    page.actions.key_down('ctrl').type('a').key_up('ctrl')
"""
from __future__ import annotations

import json as _json

from ..core import INT, NUM, STR, ToolResult, registry, schema
from ..session import SESSION

#: 支持的动作名 → 说明（用于描述与报错提示）
SUPPORTED_ACTIONS = {
    'move_to': '移动到目标（元素或坐标），可带 offset_x/offset_y/duration',
    'move': '相对当前位置移动 offset_x/offset_y，可带 duration',
    'click': '左键单击（可带 target 先移动再点）',
    'r_click': '右键单击',
    'm_click': '中键单击',
    'hold': '按下左键（可带 target）',
    'release': '松开左键',
    'r_hold': '按下右键',
    'r_release': '松开右键',
    'm_hold': '按下中键',
    'm_release': '松开中键',
    'type': '输入文本（依次敲键）',
    'input': '输入文本（整段）',
    'key_down': '按下修饰键，如 ctrl / shift / alt',
    'key_up': '松开修饰键',
    'scroll': '滚轮滚动 delta_y / delta_x，可带 target',
    'down': '滚轮向下 pixel 像素',
    'up': '滚轮向上 pixel 像素',
    'left': '滚轮向左 pixel 像素',
    'right': '滚轮向右 pixel 像素',
    'wait': '等待 second 秒',
}

#: 需要 target 的动作（给了更精确，没给也能执行）
_TARGET_OPTIONAL = {'move_to', 'click', 'r_click', 'm_click', 'hold', 'scroll'}


def _resolve_target(actions_obj, step: dict):
    """把 step 里的 target 解析成「元素对象」或「(x, y) 坐标」。"""
    element_id = step.get('element_id')
    selector = step.get('selector')
    if element_id:
        return SESSION.get_element(element_id)
    if selector:
        tab = SESSION.resolve_tab()
        ele = tab.ele(selector)
        if not ele:
            raise ValueError(f'动作目标未找到：{selector}')
        return ele
    # 也允许直接给坐标
    if step.get('x') is not None and step.get('y') is not None:
        return (float(step['x']), float(step['y']))
    return None


@registry.tool(
    name='dp_action_chain',
    description=(
        '按顺序执行一串鼠标/键盘动作（对应 DrissionPage 的 page.actions 动作链）。\n'
        '适用：滑块验证码拖拽、Ctrl+A 等组合键、画布/地图按坐标操作、按住拖动。\n'
        '每个动作是一个对象，action 为动作名，其余为参数。支持的动作：\n'
        + '；'.join(f'{k}（{v}）' for k, v in SUPPORTED_ACTIONS.items()) + '。\n'
        'target 写法：element_id=元素句柄 / selector=定位串 / x+y=视口坐标。\n'
        '示例（滑块拖拽）：[{"action":"move_to","element_id":"e1"},{"action":"hold"},'
        '{"action":"move","offset_x":300,"duration":1.5},{"action":"release"}]\n'
        '示例（全选）：[{"action":"key_down","key":"ctrl"},{"action":"type","text":"a"},'
        '{"action":"key_up","key":"ctrl"}]'
    ),
    input_schema=schema(
        steps=STR('动作序列（JSON 数组）', required=True),
        duration=NUM('默认动作时长秒数，未在动作里指定时使用，默认 0.5', default=0.5),
        release_on_error=STR('出错时是否自动松开按键，默认 true', enum=['true', 'false'], default='true'),
    ),
    group='element',
    mutating=True,
)
def dp_action_chain(args: dict) -> ToolResult:
    raw = args.get('steps')
    try:
        if isinstance(raw, str):
            steps = _json.loads(raw)
        else:
            steps = raw
    except ValueError as exc:
        return ToolResult.fail(f'steps 不是合法 JSON：{exc}')

    if not isinstance(steps, list) or not steps:
        return ToolResult.fail('steps 必须是非空数组')

    default_duration = float(args.get('duration') or 0.5)
    release_on_error = str(args.get('release_on_error', 'true')).lower() != 'false'

    tab = SESSION.resolve_tab()
    actions = tab.actions
    executed = []
    pressed = []          # 记录按下的键/鼠标键，出错时回滚

    try:
        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f'第 {idx} 个动作不是对象')
            name = (step.get('action') or '').strip()
            if not name:
                raise ValueError(f'第 {idx} 个动作缺少 action')
            if name not in SUPPORTED_ACTIONS:
                raise ValueError(
                    f'第 {idx} 个动作不支持：{name}；'
                    f'可用动作：{", ".join(SUPPORTED_ACTIONS)}'
                )

            target = _resolve_target(actions, step) if name in _TARGET_OPTIONAL else None
            duration = float(step.get('duration') or default_duration)

            if name == 'move_to':
                if target is None:
                    raise ValueError(f'第 {idx} 个 move_to 缺少目标')
                actions.move_to(target, offset_x=step.get('offset_x', 0),
                                offset_y=step.get('offset_y', 0), duration=duration)
            elif name == 'move':
                actions.move(offset_x=step.get('offset_x', 0),
                             offset_y=step.get('offset_y', 0), duration=duration)
            elif name == 'click':
                actions.click(target) if target is not None else actions.click()
            elif name == 'r_click':
                actions.r_click(target) if target is not None else actions.r_click()
            elif name == 'm_click':
                actions.m_click(target) if target is not None else actions.m_click()
            elif name == 'hold':
                actions.hold(target) if target is not None else actions.hold()
                pressed.append('mouse-left')
            elif name == 'release':
                actions.release(target) if target is not None else actions.release()
                if 'mouse-left' in pressed:
                    pressed.remove('mouse-left')
            elif name == 'r_hold':
                actions.r_hold(target) if target is not None else actions.r_hold()
                pressed.append('mouse-right')
            elif name == 'r_release':
                actions.r_release(target) if target is not None else actions.r_release()
                if 'mouse-right' in pressed:
                    pressed.remove('mouse-right')
            elif name == 'm_hold':
                actions.m_hold(target) if target is not None else actions.m_hold()
                pressed.append('mouse-middle')
            elif name == 'm_release':
                actions.m_release(target) if target is not None else actions.m_release()
                if 'mouse-middle' in pressed:
                    pressed.remove('mouse-middle')
            elif name in ('type', 'input'):
                text = step.get('text')
                if text is None:
                    raise ValueError(f'第 {idx} 个 {name} 缺少 text')
                actions.type(text) if name == 'type' else actions.input(text)
            elif name == 'key_down':
                key = step.get('key')
                if not key:
                    raise ValueError(f'第 {idx} 个 key_down 缺少 key')
                actions.key_down(key)
                pressed.append(f'key:{key}')
            elif name == 'key_up':
                key = step.get('key')
                if not key:
                    raise ValueError(f'第 {idx} 个 key_up 缺少 key')
                actions.key_up(key)
                if f'key:{key}' in pressed:
                    pressed.remove(f'key:{key}')
            elif name == 'scroll':
                actions.scroll(delta_y=step.get('delta_y', 0),
                               delta_x=step.get('delta_x', 0), on_ele=target)
            elif name in ('down', 'up', 'left', 'right'):
                pixel = step.get('pixel', step.get('value', 100))
                getattr(actions, name)(pixel)
            elif name == 'wait':
                actions.wait(float(step.get('second') or step.get('seconds') or 0.5))

            executed.append(name)

    except Exception as exc:
        # 出错时尽量把按住的键/鼠标松开，避免浏览器停在「按住」状态
        if release_on_error:
            for item in reversed(pressed):
                try:
                    if item.startswith('key:'):
                        actions.key_up(item.split(':', 1)[1])
                    elif item.endswith('right'):
                        actions.r_release()
                    elif item.endswith('middle'):
                        actions.m_release()
                    else:
                        actions.release()
                except Exception:
                    pass
        return ToolResult.fail(
            f'动作链在第 {len(executed) + 1} 步失败：{type(exc).__name__}: {exc}；'
            f'已执行 {executed}'
        )

    return ToolResult.ok(
        data={'executed': executed, 'steps': len(executed)},
        text=f'动作链执行完成，共 {len(executed)} 步',
    )


@registry.tool(
    name='dp_slider_drag',
    description=(
        '滑块验证码的拖拽动作（动作链的常用封装）：移动到滑块 → 按住 → 平移 → 松开。\n'
        'track 可传多段位移以模拟非匀速轨迹，例如 [{"offset":120,"duration":0.4},'
        '{"offset":80,"duration":0.3}]，比匀速平移更像真人。\n'
        '注意：本工具只做「拖动」，不负责识别缺口位置——缺口坐标需由视觉/接口另行得到。'
    ),
    input_schema=schema(
        element_id=STR('滑块元素句柄'),
        selector=STR('滑块定位串（与 element_id 二选一）'),
        distance=INT('总平移像素（与 track 二选一）'),
        track=STR('分段轨迹（JSON 数组），每段 {offset, duration, offset_y?}'),
        duration=NUM('总时长秒数，默认 1.5', default=1.5),
        offset_y=INT('纵向偏移，默认 0', default=0),
    ),
    group='element',
    mutating=True,
)
def dp_slider_drag(args: dict) -> ToolResult:
    try:
        if args.get('element_id'):
            slider = SESSION.get_element(args['element_id'])
        elif args.get('selector'):
            tab = SESSION.resolve_tab()
            slider = tab.ele(args['selector'])
            if not slider:
                return ToolResult.fail(f"未找到滑块：{args['selector']}")
        else:
            return ToolResult.fail('必须提供 element_id 或 selector')
    except Exception as exc:
        return ToolResult.fail(str(exc))

    raw_track = args.get('track')
    if raw_track:
        try:
            track = _json.loads(raw_track) if isinstance(raw_track, str) else raw_track
        except ValueError as exc:
            return ToolResult.fail(f'track 不是合法 JSON：{exc}')
        if not isinstance(track, list) or not track:
            return ToolResult.fail('track 必须是非空数组')
    else:
        distance = args.get('distance')
        if distance is None:
            return ToolResult.fail('必须提供 distance 或 track')
        track = [{'offset': int(distance), 'duration': float(args.get('duration') or 1.5)}]

    tab = SESSION.resolve_tab()
    actions = tab.actions
    offset_y = int(args.get('offset_y') or 0)

    try:
        actions.move_to(slider, duration=0.3)
        actions.hold()
        moved = 0
        for seg in track:
            offset = int(seg.get('offset') or 0)
            seg_y = int(seg.get('offset_y', offset_y))
            seg_duration = float(seg.get('duration') or 0.4)
            actions.move(offset_x=offset, offset_y=seg_y, duration=seg_duration)
            moved += offset
        actions.release()
    except Exception as exc:
        try:
            actions.release()
        except Exception:
            pass
        return ToolResult.fail(f'拖动失败：{type(exc).__name__}: {exc}')

    return ToolResult.ok(
        data={'moved': moved, 'segments': len(track)},
        text=f'已拖动滑块，累计平移 {moved} 像素',
    )
