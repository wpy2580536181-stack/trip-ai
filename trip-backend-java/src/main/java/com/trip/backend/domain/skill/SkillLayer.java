package com.trip.backend.domain.skill;

/**
 * 技能层级：三层渐进式披露
 *
 * - L1 目录层：轻量元信息，常驻上下文
 * - L2 规格层：完整 SKILL.md，被选中才加载
 * - L3 执行层：执行时按需读取 resources
 */
public enum SkillLayer {
    /** 目录层：name/description/tags/kind */
    L1,
    /** 规格层：trigger/instructions/input_schema/examples/body */
    L2,
    /** 执行层：references/scripts/assets 资源 */
    L3
}
