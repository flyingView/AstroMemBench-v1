"""SCC classification and the reviewed scenario–subchallenge template catalog.

This evaluator metadata describes coverage only. It never enters agent inputs.
"""
from collections import Counter
from dataclasses import asdict, dataclass

METHOD_NAME = 'Three-Dimensional SCC Design Methodology'
METHOD_NAME_ZH = 'SCC三维设计法'
INSTANCES_PER_TEMPLATE = 16
DIFFICULTY_COUNTS = {'easy': 6, 'medium': 6, 'hard': 4}


@dataclass(frozen=True)
class Node:
    name: str
    english: str
    parent: str | None = None


@dataclass(frozen=True)
class Template:
    name: str
    subchallenge: str
    mission: str
    capabilities: tuple[str, ...]

    @property
    def challenge(self):
        return SUBCHALLENGES[self.subchallenge].parent

    @property
    def craft(self):
        return MISSIONS[self.mission].parent

    @property
    def english(self):
        return f'{SUBCHALLENGES[self.subchallenge].english}: {MISSIONS[self.mission].english}'

    def to_dict(self):
        return {**asdict(self), 'capabilities': list(self.capabilities),
                'challenge': self.challenge, 'craft': self.craft, 'english': self.english}


CHALLENGES = {
    'C': Node('通信时延', 'Communication delays'),
    'T': Node('时间关键操作', 'Time-critical operations'),
    'E': Node('环境不确定性', 'Environmental uncertainty'),
    'I': Node('复杂物理交互', 'Complex physical interactions'),
    'R': Node('功率与计算资源约束', 'Power constraints and computational resources'),
    'S': Node('安全与可靠性', 'Safety and reliability'),
}
SUBCHALLENGES = {
    'C1': Node('指示中断时的已有要求遵守', 'Adherence to existing requirements during instruction interruptions', 'C'),
    'C2': Node('指示到达混乱时的规则消歧', 'Rule disambiguation under out-of-order instruction arrival', 'C'),
    'C3': Node('发送消息完成的确定', 'Determination of message transmission completion', 'C'),
    'T1': Node('时效有效性判断', 'Temporal validity assessment', 'T'),
    'T2': Node('未来义务召回', 'Recall of future obligations', 'T'),
    'E1': Node('已知环境下的经验匹配', 'Experience matching in known environments', 'E'),
    'E2': Node('环境变化后的旧经验修订', 'Revision of prior experience after environmental changes', 'E'),
    'E3': Node('利用已有环境记忆恢复定位', 'Localization recovery using existing environmental memory', 'E'),
    'I1': Node('单次复杂操作维护', 'State maintenance for a single complex operation', 'I'),
    'I2': Node('多操作复杂任务维护', 'State maintenance for complex tasks involving multiple operations', 'I'),
    'R1': Node('历史能耗经验的利用', 'Use of historical energy consumption experience', 'R'),
    'R2': Node('后续用电需求的预留', 'Energy reservation for future needs', 'R'),
    'R3': Node('已有计算结果的复用', 'Reuse of existing computation results', 'R'),
    'S1': Node('安全前提的有效确认', 'Confirmation of valid safety prerequisites', 'S'),
    'S2': Node('功能变化后的能力更新', 'Capability updates following functional changes', 'S'),
    'S3': Node('故障恢复后的任务接续', 'Task continuation after fault recovery', 'S'),
}
CRAFT = {
    'P': Node('星表航天器', 'Planetary surface spacecraft'),
    'O': Node('在轨服务航天器', 'On-orbit servicing spacecraft'),
    'D': Node('深空探索航天器', 'Deep-space exploration spacecraft'),
}
MISSIONS = {
    'P1': Node('区域勘察', 'Regional surveying', 'P'),
    'P2': Node('定点采样', 'Site-specific sampling', 'P'),
    'P3': Node('物资转运', 'Cargo transport', 'P'),
    'O1': Node('目标巡检', 'Target inspection', 'O'),
    'O2': Node('设备维修', 'Equipment maintenance', 'O'),
    'O3': Node('在轨补给', 'On-orbit resupply', 'O'),
    'D1': Node('巡航保障', 'Cruise support', 'D'),
    'D2': Node('科学观测', 'Scientific observation', 'D'),
    'D3': Node('数据回传', 'Data downlink', 'D'),
}
CAPABILITIES = {
    'L01': Node('感知判读', 'Perceptual interpretation'),
    'L02': Node('空间导航', 'Spatial navigation'),
    'L03': Node('观测采集', 'Observation acquisition'),
    'L04': Node('机械操作', 'Mechanical manipulation'),
    'L05': Node('运行调控', 'Operational regulation'),
    'L06': Node('设备配置', 'Equipment configuration'),
    'L07': Node('数据处理', 'Data processing'),
    'L08': Node('通信传输', 'Communication and transmission'),
    'L09': Node('任务规划', 'Task planning'),
    'L10': Node('资源分配', 'Resource allocation'),
}
EXCLUDED_CELLS = {
    ('E3', 'D3'): '候选任务转为通信传感器辅助导航，与正常回传目标耦合不足。',
    ('I1', 'D3'): '复杂实体关系维护需要额外拆装，实质转向维修或装配。',
    ('I2', 'D3'): '真实物理累计候选偏机构维护，字节累计不属于累计物理作用。',
    ('I2', 'O1'): '累计辐照损伤需额外材料与工况假设，正常巡检中关联弱。',
}
# Explicitly reviewed names, in P1/P2/P3/O1/O2/O3/D1/D2/D3 order.
_TEMPLATE_NAMES = {
    'C1': ('失联勘察中的分区采集清单保持', '失联后的样品分装要求保持', '失联转运中的分阶段货物处置要求',
           '失联期间的巡检规则保持', '失联维修中的工序作业要求保持', '失联补给中的单段注入许可保持',
           '失联后的平台轮巡要求保持', '失联科学观测中的配套采集指示保持', '指示中断后的回传处理约束保持'),
    'C2': ('乱序勘察指示的字段重建', '采样分装配额的乱序修订', '物资交付舱位的乱序互换清单',
           '巡检工单项目的乱序增删', '依赖指定底稿的维修修订单', '在轨补给指令包的原子切换',
           '巡航指令的分级管辖与字段让位', '科学观测的范围内版本消歧', '乱序路由指示下的数据回传'),
    'C3': ('区域地图的分片交付与整带清理', '样品保管链凭证交接', '转运货单的双端交接确认',
           '巡检报告与共享原图的确认依赖', '三项维修的验收资料状态交接', '补给计量账册的连续确认前缀',
           '巡航遥测环形页的确认后轮换', '科学观测包的多站归档门槛', '数据回传的发送、确认与清理'),
    'T1': ('光照许可下的测量子集', '采样后成分保持期内的分析选择', '冷藏暂停计时后的物资转运',
           '巡检复拍的有效比较间隔', '维修胶料适用期与施工方案选择', '对接阶段的分段注入许可',
           '巡航校时老化后的定时触发', '周期遮挡中的完整科学曝光', '下传窗口过期后的计划处置'),
    'T2': ('勘察复访点的事件触发义务', '采样后保全义务与连续登记', '转运交接节点的后续责任',
           '连续巡检中的计次复看义务', '维修工序后延迟复检', '补给完成后的延迟留样与回弹读数',
           '巡航保障中的定时义务召回', '观测块之后的配套背景采集', '释放时刻之后的首个回传机会'),
    'E1': ('已知勘察条件对应的经验取用', '分层样柱的经验组合', '去程货物与返程周转箱的经验组合',
           '巡检表面成像经验', '维修工艺经验的适用区间', '混合比例与接收结构对应的定量补给经验',
           '周期热环境形态对应的巡航保障经验', '工况匹配后取用谱段验收经验', '链路工况下的有效回传曲线取用'),
    'E2': ('地表变化后的巡测转位', '覆层变化后的标志层取芯', '运输路线环境认识更新',
           '外表照明变化后的巡检曝光', '工位净空变化后的维修头选择', '接收环境压力变化后的补给分流',
           '粒子方向场变化后的巡航遮蔽', '背景场变化后的科学谱段扣除', '传播环境变化后的回传档位'),
    'E3': ('地标勘察档案中的作业区定位恢复', '地标与采样导轨子位的联合定位', '重复地貌中的运输环线定位',
           '重复面板的有限补测定位', '检修通道的朝向不变定位', '补给接近单元的距离与侧向联合定位',
           '共同钟偏下的巡航区段定位恢复', '科学观测遮挡图的空间交集定位', None),
    'I1': ('勘察测头与载架的嵌套装接关系', '吹扫与采集支路迁移', '转运列车的实际挂接图与指定车厢分离',
           '巡检探缆的导环穿引关系', '维修替换件的支撑交接', '补给管路连接状态维护',
           '巡航冷却支路的实际并联连接', '科学观测光路的两级实体导光关系', None),
    'I2': ('重复勘察碾压的车辙累计与下一闭合测线', '同一采样点的累计钻进维护', '连续装卸后的载车质量与力矩维护',
           None, '共享打磨带在双修复区的累计去除', '接收单元累计注入、实际回抽与目标收口',
           '巡航反作用轮累计角动量与卸载', '科学探测器积分井电荷与读出增益', None),
    'R1': ('区域测线闭合勘察的能耗经验', '定点取样的空载去程与装样返程', '运输中的历史能耗经验利用',
           '巡检采集程序的覆盖与实际耗电', '批量紧固维修的启动与单件能耗经验', '分压力段补给的泵耗电与切换损失',
           '巡航热控周期的历史功耗利用', '单次科学采集的历史耗电与终局产出', '报文合批回传的启动与块传输能耗'),
    'R2': ('区域勘察的双电源后续任务预留', '采样规模与固定保全工序的非线性电量预算', '高优运输预留后的本次整件交付组合',
           '巡检批次的未完检查单元用电', '维修后续工单的共享启动费用', '在轨补给通道启用后的必需收尾用电',
           '巡航补能前后两阶段的高优供电', '科学观测中的后续高优作业电量预留', '互斥通信后续流程的保证供电预算'),
    'R3': ('局部勘察地图配准变换链复用', '取样头分段标定曲线的复用', '货舱模块惯量结果的装配复用',
           '重叠巡检图块的分割结果复用', '维修参数计算结果复用', '补给支路阻力计算的串并联复用',
           '巡航双轴控制分配的分解结果复用', '科学观测批次充分统计量复用', '分块校验结果的顺序组合复用'),
    'S1': ('踏入勘察面的承载核验凭据', '分装谱系中的安全放行前提', '当前装载清单的成对兼容凭据',
           '占区登记与净空凭据', '当前安装状态下的安全前提确认', '两条隔离方案的充分安全依据',
           '独立核验链的机动放行表决', '扫描方向集合的安全覆盖证据', '发射模式与在用接收机的共存安全前提'),
    'S2': ('勘察扫描器受限视场与完整扫描程序', '样品测量功能、批量与精度的联合能力', '功能变化后的两货物联合分配',
           '巡检功能变化后的能力更新', '维修工具的转矩—转速能力包络', '补给链路中泵与介质适配器的能力组合',
           '姿态执行通道降额后的可达控制量', '科学观测通道变化后的可观测性', '编码固件变化后的整条回传处理能力'),
    'S3': ('覆盖图恢复后的勘察足迹接续', '采样故障后的真实进度接续', '转运保管状态恢复后的批量接续',
           '巡检成果持久化边界下的任务接续', '维修恢复后的双臂作业分派', '补给计量成果与收尾状态的恢复接续',
           '巡航动量卸载脉冲序列的故障后接续', '配对曝光成果在故障后的接续', '接收端持久进度下的回传窗口恢复'),
}
# Capability associations for the fixed task catalog.
# A template label does not imply that every one of its instances uses that capability.
_CAPABILITY_ROWS = {
    'C1': '03 03/04 04 02/03 04/06 05/06 03/07 03 07/08',
    'C2': '03 04 04/09 03/09 04 05 05/08 03 07/08',
    'C3': '07/08/09 07/08/09 07/08/09 07/08/09 07/08/09 07/08/09 07/08/09 07/08/09 07/08/09',
    'T1': '03/09 03/09 02/10 07 04/09 05/09 06/09 03/09 08',
    'T2': '03/04/09 03/04/05/07/09 02/04/09 03/09 03/07/09 03/04/05/09 03/06/07/09 03/09 07/08/09',
    'E1': '03/06 04/06 05/06 03/06 04/06 05/06 01/05/06 03/06 06/08',
    'E2': '02/10 04 02 03/06 04/06 05/10 02/05 01/03/07 06/08',
    'E3': '01/02 01/02 01/02 01/02/03/09 01/02 01/02 01/02 01/02 -',
    'I1': '02/04 04 04/09 04 04 04 05/06 03 -',
    'I2': '02/10 04 02/04 - 04/06 05/10 05 03/06 -',
    'R1': '02/09/10 02/10 02/10 03/09/10 04/06/10 05/06/09/10 05/09/10 03/10 07/08/09/10',
    'R2': '03/10 04/10 04/09/10 03/10 04/10 05/06/10 03/10 03/10 08/10',
    'R3': '02/07/10 07/10 07/10 07/10 07/10 07/10 07/10 07/10 07/10',
    'S1': '02 04 02 03 04 04 05 03 08',
    'S2': '03 03 04/09/10 03 04/06 05/06 05 03/06 06/07/08',
    'S3': '03/09 04/07 04/09 03/07 04/09/10 04/05/07 05 03 08/09',
}
TEMPLATE_SPECS = {
    f'FM-{challenge}-{mission}': Template(name, challenge, mission, tuple('L' + value for value in tags.split('/')))
    for challenge, names in _TEMPLATE_NAMES.items()
    for mission, name, tags in zip(MISSIONS, names, _CAPABILITY_ROWS[challenge].split(), strict=True)
    if name is not None
}
APPLICABILITY = {challenge: {mission: ('excluded' if (challenge, mission) in EXCLUDED_CELLS else 'applicable')
                            for mission in MISSIONS} for challenge in SUBCHALLENGES}
TOTAL_INSTANCES = len(TEMPLATE_SPECS) * INSTANCES_PER_TEMPLATE


def is_complete_bank(tasks):
    identities = [task.case_id for task in tasks]
    expected = {f'{template}-{i:03d}' for template in TEMPLATE_SPECS for i in range(1, INSTANCES_PER_TEMPLATE + 1)}
    return len(identities) == len(expected) and set(identities) == expected


def coverage_targets():
    return {'method': 'SCC',
            'challenges': {k: asdict(v) for k, v in CHALLENGES.items()},
            'subchallenges': {k: asdict(v) for k, v in SUBCHALLENGES.items()},
            'craft': {k: asdict(v) for k, v in CRAFT.items()},
            'missions': {k: asdict(v) for k, v in MISSIONS.items()},
            'capabilities': {k: asdict(v) for k, v in CAPABILITIES.items()},
            'templates': {k: v.to_dict() for k, v in TEMPLATE_SPECS.items()},
            'applicability': {k: dict(v) for k, v in APPLICABILITY.items()},
            'exclusions': [{'subchallenge': c, 'mission': m, 'reason': reason} for (c, m), reason in EXCLUDED_CELLS.items()],
            'capability_counts': dict(Counter(c for t in TEMPLATE_SPECS.values() for c in t.capabilities)),
            'template_count': len(TEMPLATE_SPECS), 'instance_count': TOTAL_INSTANCES,
            'instances_per_template': INSTANCES_PER_TEMPLATE, 'difficulty_counts': dict(DIFFICULTY_COUNTS)}


def group_cases(cases, axis):
    """Use frozen classification; capability associations overlap by design."""
    if axis not in {'challenge', 'subchallenge', 'craft', 'mission', 'template', 'difficulty', 'capability'}:
        raise ValueError(f'Unknown coverage axis: {axis}')
    groups = {}
    for case in cases:
        spec = case.design['classification']
        labels = spec['capabilities'] if axis == 'capability' else [
            getattr(case, axis) if axis in {'template', 'difficulty'} else spec[axis]]
        for label in labels:
            groups.setdefault(label, {})[case.case_id] = case
    return {label: list(rows.values()) for label, rows in sorted(groups.items())}
