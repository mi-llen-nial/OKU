const ICONS_VERSION = "20260302-2";
const ILLUSTRATIONS_VERSION = "20260322-1";
const LOGO_VERSION = "20260312-1";

export const assetPaths = {
  logo: {
    png: `/assets/logo/logo.png?v=${LOGO_VERSION}`,
    svg: `/assets/logo/logo.svg?v=${LOGO_VERSION}`,
    textBlack: `/assets/logo/OKU_black.svg?v=${LOGO_VERSION}`,
    textColor: `/assets/logo/OKU_color.svg?v=${LOGO_VERSION}`,
  },
  icons: {
    plus: `/assets/icons/material-symbols_add-rounded.svg?v=${ICONS_VERSION}`,
    wand: `/assets/icons/wand.svg?v=${ICONS_VERSION}`,
    book: `/assets/icons/book.svg?v=${ICONS_VERSION}`,
    spark: `/assets/icons/spark.svg?v=${ICONS_VERSION}`,
    repeat: `/assets/icons/mi_repeat.svg?v=${ICONS_VERSION}`,
    weakTopic: `/assets/icons/lucide_arrow-up.svg?v=${ICONS_VERSION}`,
    lesson: `/assets/icons/streamline_class-lesson-solid.svg?v=${ICONS_VERSION}`,
    text: `/assets/icons/si_text-fill.svg?v=${ICONS_VERSION}`,
    headphones: `/assets/icons/ic_round-headphones.svg?v=${ICONS_VERSION}`,
    microphone: `/assets/icons/tabler_microphone-filled.svg?v=${ICONS_VERSION}`,
    math: `/assets/icons/tabler_math-symbols.svg?v=${ICONS_VERSION}`,
    algebra: `/assets/icons/tabler_math.svg?v=${ICONS_VERSION}`,
    geometry: `/assets/icons/tabler_geometry.svg?v=${ICONS_VERSION}`,
    physics: `/assets/icons/streamline-plump_atom-remix.svg?v=${ICONS_VERSION}`,
    english: `/assets/icons/meteor-icons_language.svg?v=${ICONS_VERSION}`,
    russian: `/assets/icons/material-symbols_dictionary-rounded.svg?v=${ICONS_VERSION}`,
    history: `/assets/icons/material-symbols_history-edu-rounded.svg?v=${ICONS_VERSION}`,
    biology: `/assets/icons/streamline_bacteria-virus-cells-biology-solid.svg?v=${ICONS_VERSION}`,
    chemistry: `/assets/icons/material-symbols_biotech-rounded.svg?v=${ICONS_VERSION}`,
    informatics: `/assets/icons/solar_cpu-bold.svg?v=${ICONS_VERSION}`,
    ent: `/assets/icons/healthicons_i-exam-multiple-choice.svg?v=${ICONS_VERSION}`,
    ielts: `/assets/icons/ri_english-input.svg?v=${ICONS_VERSION}`,
    blitz: `/assets/icons/ph_lightning-fill.svg?v=${ICONS_VERSION}`,
    soon: `/assets/icons/solar_server-square-update-outline.svg?v=${ICONS_VERSION}`,
    group: `/assets/icons/material-symbols_group-rounded.svg?v=${ICONS_VERSION}`,
    student: `/assets/icons/material-symbols_group-rounded-1.svg?v=${ICONS_VERSION}`,
    groupEdit: `/assets/icons/cuida_edit-outline.svg?v=${ICONS_VERSION}`,
    groupDelete: `/assets/icons/mdi_trash.svg?v=${ICONS_VERSION}`,
    sidebarArrow: `/assets/icons/arrow.svg?v=${ICONS_VERSION}`,
    questionAnswer: `/assets/icons/ic_round-question-answer.svg?v=${ICONS_VERSION}`,
    warningDiamond: `/assets/icons/mynaui_danger-diamond-solid.svg?v=${ICONS_VERSION}`,
    schedule: `/assets/icons/uis_schedule.svg?v=${ICONS_VERSION}`,
    timer: `/assets/icons/mingcute_time-fill.svg?v=${ICONS_VERSION}`,
    /** Списки с отметками (педагог, цены) */
    checkFill: `/assets/icons/mingcute_check-fill.svg?v=${ICONS_VERSION}`,
    aiGenerate: `/assets/icons/octicon_north-star-16.svg?v=${ICONS_VERSION}`,
    attachFile: `/assets/icons/tabler_link.svg?v=${ICONS_VERSION}`,
    testCreated: `/assets/icons/icon-park-solid_inbox-success.svg?v=${ICONS_VERSION}`,
    testPassed: `/assets/icons/icon-park-solid_success.svg?v=${ICONS_VERSION}`,
    /** Блок «Это актуально» на лендинге */
    landingStatUsers: `/assets/icons/material-symbols_group-rounded.svg?v=${ICONS_VERSION}`,
    /** «всего от 660 тг» — иконка «образование / выпускная шапочка» по макету */
    landingStatPrice: `/assets/icons/material-symbols_history-edu-rounded.svg?v=${ICONS_VERSION}`,
    landingStatEfficiency: `/assets/icons/akar-icons_statistic-up.svg?v=${ICONS_VERSION}`,
    landingStatTests: `/assets/icons/healthicons_i-exam-multiple-choice.svg?v=${ICONS_VERSION}`,
    /** Страница «Ученику»: средняя школа */
    school: `/assets/icons/ic_round-school.svg?v=${ICONS_VERSION}`,
    middleSchool: `/assets/icons/middle_school.svg?v=${ICONS_VERSION}`,
    highSchool: `/assets/icons/high_school.svg?v=${ICONS_VERSION}`,
  },
  images: {
    parchment: "/assets/images/bg-parchment.svg",
    arcaneFrame: "/assets/images/arcane-frame.svg",
    qrOku: "/assets/images/t_me-KOMA_OKU_bot%201.png",
    qrFaq: "/assets/images/FAQ_bot.png",
    /** Страница «Педагогу»: иллюстрации режимов (ручной / AI / файл) */
    teachersModeManual: `/assets/images/with_hand.svg?v=${ICONS_VERSION}`,
    teachersModeAi: `/assets/images/with_ai.svg?v=${ICONS_VERSION}`,
    teachersModeFile: `/assets/images/with_file.svg?v=${ICONS_VERSION}`,
  },
  illustrations: {
    owl: `/assets/illustrations/illus-owl.svg?v=${ILLUSTRATIONS_VERSION}`,
    constellation: `/assets/illustrations/illus-constellation.svg?v=${ILLUSTRATIONS_VERSION}`,
    /** Миссия: стопка книг */
    landingBooks: `/assets/illustrations/Untitled%201.png?v=${ILLUSTRATIONS_VERSION}`,
    /** «Что такое OKU»: ученик / преподаватель / учреждение (макет Figma) */
    landingModernTest: `/assets/illustrations/modern_test.png?v=${ILLUSTRATIONS_VERSION}`,
    landingMainTeacher: `/assets/illustrations/main_teacher.png?v=${ILLUSTRATIONS_VERSION}`,
    landingMainOrg: `/assets/illustrations/main_org.png?v=${ILLUSTRATIONS_VERSION}`,
    /** Страница «Ученику»: карточки предметов */
    studentAlgebra: `/assets/illustrations/algebra.svg?v=${ILLUSTRATIONS_VERSION}`,
    studentGeometry: `/assets/illustrations/geometry.svg?v=${ILLUSTRATIONS_VERSION}`,
    studentPhysics: `/assets/illustrations/physics.svg?v=${ILLUSTRATIONS_VERSION}`,
    studentBiology: `/assets/illustrations/bio.svg?v=${ILLUSTRATIONS_VERSION}`,
    studentInformatics: `/assets/illustrations/computer.svg?v=${ILLUSTRATIONS_VERSION}`,
    studentEnglish: `/assets/illustrations/english.svg?v=${ILLUSTRATIONS_VERSION}`,
    studentHistory: `/assets/illustrations/history.svg?v=${ILLUSTRATIONS_VERSION}`,
    /** «Общеобразовательные предметы» */
    studentGeneralSubjects: `/assets/illustrations/iconsfsad%202.png?v=${ILLUSTRATIONS_VERSION}`,
    /** «Персонализированное обучение» */
    studentSphere: `/assets/illustrations/sphere.svg?v=${ILLUSTRATIONS_VERSION}`,
  },
  audio: {
    placeholder: "/assets/audio/.gitkeep",
  },
} as const;

export type AssetPaths = typeof assetPaths;
