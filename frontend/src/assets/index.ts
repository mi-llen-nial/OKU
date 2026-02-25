export const assetPaths = {
  logo: {
    png: "/assets/logo/logo.png",
    svg: "/assets/logo/logo.svg",
  },
  icons: {
    wand: "/assets/icons/wand.svg",
    book: "/assets/icons/book.svg",
    spark: "/assets/icons/spark.svg",
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
