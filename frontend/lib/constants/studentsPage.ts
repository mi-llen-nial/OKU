import { assetPaths } from "@/src/assets";

export interface StudentSubjectItem {
  id: string;
  illustrationSrc: string;
  titleRu: string;
  titleKz: string;
}

export const STUDENTS_SUBJECTS_ROW_1: StudentSubjectItem[] = [
  {
    id: "algebra",
    illustrationSrc: assetPaths.illustrations.studentAlgebra,
    titleRu: "Алгебра",
    titleKz: "Алгебра",
  },
  {
    id: "geometry",
    illustrationSrc: assetPaths.illustrations.studentGeometry,
    titleRu: "Геометрия",
    titleKz: "Геометрия",
  },
  {
    id: "physics",
    illustrationSrc: assetPaths.illustrations.studentPhysics,
    titleRu: "Физика",
    titleKz: "Физика",
  },
  {
    id: "biology",
    illustrationSrc: assetPaths.illustrations.studentBiology,
    titleRu: "Биология",
    titleKz: "Биология",
  },
];

export const STUDENTS_SUBJECTS_ROW_2: StudentSubjectItem[] = [
  {
    id: "informatics",
    illustrationSrc: assetPaths.illustrations.studentInformatics,
    titleRu: "Информатика",
    titleKz: "Информатика",
  },
  {
    id: "english",
    illustrationSrc: assetPaths.illustrations.studentEnglish,
    titleRu: "Английский язык",
    titleKz: "Ағылшын тілі",
  },
  {
    id: "history",
    illustrationSrc: assetPaths.illustrations.studentHistory,
    titleRu: "Всемирная история",
    titleKz: "Дүние жүзі тарихы",
  },
  {
    id: "algebra-2",
    illustrationSrc: assetPaths.illustrations.studentAlgebra,
    titleRu: "Алгебра",
    titleKz: "Алгебра",
  },
];

/** Три ряда маркиза на узких экранах (по ~3 плашки) */
export const STUDENTS_SUBJECTS_MOBILE_ROW_1: StudentSubjectItem[] = [
  STUDENTS_SUBJECTS_ROW_1[0],
  STUDENTS_SUBJECTS_ROW_1[1],
  STUDENTS_SUBJECTS_ROW_1[2],
];

export const STUDENTS_SUBJECTS_MOBILE_ROW_2: StudentSubjectItem[] = [
  STUDENTS_SUBJECTS_ROW_1[3],
  STUDENTS_SUBJECTS_ROW_2[0],
  STUDENTS_SUBJECTS_ROW_2[1],
];

export const STUDENTS_SUBJECTS_MOBILE_ROW_3: StudentSubjectItem[] = [
  STUDENTS_SUBJECTS_ROW_2[2],
  STUDENTS_SUBJECTS_ROW_2[3],
  {
    id: "geometry-loop",
    illustrationSrc: assetPaths.illustrations.studentGeometry,
    titleRu: "Геометрия",
    titleKz: "Геометрия",
  },
];
