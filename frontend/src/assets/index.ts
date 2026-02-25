const ICONS_VERSION = "20260225-3";

export const assetPaths = {
  logo: {
    png: "/assets/logo/logo.png",
    svg: "/assets/logo/logo.svg",
  },
  icons: {
    wand: `/assets/icons/wand.svg?v=${ICONS_VERSION}`,
    book: `/assets/icons/book.svg?v=${ICONS_VERSION}`,
    spark: `/assets/icons/spark.svg?v=${ICONS_VERSION}`,
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
    soon: `/assets/icons/solar_server-square-update-outline.svg?v=${ICONS_VERSION}`,
  },
  images: {
    parchment: "/assets/images/bg-parchment.svg",
    arcaneFrame: "/assets/images/arcane-frame.svg",
  },
  illustrations: {
    owl: "/assets/illustrations/illus-owl.svg",
    constellation: "/assets/illustrations/illus-constellation.svg",
  },
  audio: {
    placeholder: "/assets/audio/.gitkeep",
  },
} as const;

export type AssetPaths = typeof assetPaths;
