const ICONS_VERSION = "20260302-1";
const ILLUSTRATIONS_VERSION = "20260301-2";

export const assetPaths = {
  logo: {
    png: "/assets/logo/logo.png",
    svg: "/assets/logo/logo.svg",
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
  },
  images: {
    parchment: "/assets/images/bg-parchment.svg",
    arcaneFrame: "/assets/images/arcane-frame.svg",
    qrOku: "/assets/images/t_me-KOMA_OKU_bot%201.png",
    qrFaq: "/assets/images/FAQ_bot.png",
  },
  illustrations: {
    owl: `/assets/illustrations/illus-owl.svg?v=${ILLUSTRATIONS_VERSION}`,
    constellation: `/assets/illustrations/illus-constellation.svg?v=${ILLUSTRATIONS_VERSION}`,
    landingBooks: `/assets/illustrations/Untitled%201.png?v=${ILLUSTRATIONS_VERSION}`,
    landingSubjects: `/assets/illustrations/iconsfsad%201.png?v=${ILLUSTRATIONS_VERSION}`,
    landingPrep: `/assets/illustrations/gsfdkgsf%201.png?v=${ILLUSTRATIONS_VERSION}`,
    landingTeacher: `/assets/illustrations/teacher%201.png?v=${ILLUSTRATIONS_VERSION}`,
  },
  audio: {
    placeholder: "/assets/audio/.gitkeep",
  },
} as const;

export type AssetPaths = typeof assetPaths;
