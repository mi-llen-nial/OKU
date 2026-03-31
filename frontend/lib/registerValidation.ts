/** Домены одноразовой почты — регистрация запрещена */
const DISPOSABLE_EMAIL_DOMAINS = new Set([
  "mailinator.com",
  "guerrillamail.com",
  "guerrillamailblock.com",
  "sharklasers.com",
  "grr.la",
  "guerrillamail.net",
  "guerrillamail.org",
  "guerrillamail.biz",
  "10minutemail.com",
  "10minutemail.net",
  "temp-mail.org",
  "temp-mail.com",
  "temp-mail.ru",
  "yopmail.com",
  "yopmail.fr",
  "yopmail.net",
  "dispostable.com",
  "throwawaymail.com",
  "trashmail.com",
  "trashmail.de",
  "getnada.com",
  "maildrop.cc",
  "fakeinbox.com",
  "mintemail.com",
  "mailnesia.com",
  "spambog.com",
  "spamgourmet.com",
  "emailondeck.com",
  "moakt.com",
  "tempmailo.com",
]);

export type FieldHint = { ru: string; kz: string };

function emailDomain(email: string): string | null {
  const t = email.trim().toLowerCase();
  const at = t.lastIndexOf("@");
  if (at < 0 || at === t.length - 1) return null;
  return t.slice(at + 1) || null;
}

export function isDisposableEmailDomain(domain: string): boolean {
  const d = domain.toLowerCase();
  for (const blocked of DISPOSABLE_EMAIL_DOMAINS) {
    if (d === blocked || d.endsWith(`.${blocked}`)) return true;
  }
  return false;
}

/** Проверка почты: @, формат, чёрный список */
export function checkEmail(email: string): { ok: true } | { ok: false; hint: FieldHint } {
  const t = email.trim();
  if (!t) {
    return { ok: false, hint: { ru: "Введите адрес почты", kz: "Пошта мекенжайын енгізіңіз" } };
  }
  if (!t.includes("@")) {
    return {
      ok: false,
      hint: { ru: "В адресе почты должен быть символ @", kz: "Пошта мекенжайында @ таңбасы болуы керек" },
    };
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)) {
    return {
      ok: false,
      hint: { ru: "Введите корректный адрес почты", kz: "Дұрыс пошта мекенжайын енгізіңіз" },
    };
  }
  const domain = emailDomain(t);
  if (!domain) {
    return {
      ok: false,
      hint: { ru: "Введите корректный адрес почты", kz: "Дұрыс пошта мекенжайын енгізіңіз" },
    };
  }
  if (isDisposableEmailDomain(domain)) {
    return {
      ok: false,
      hint: {
        ru: "Такой почтовый сервис нельзя использовать для регистрации",
        kz: "Мұндай пошта сервисін тіркеу үшін пайдалануға болмайды",
      },
    };
  }
  return { ok: true };
}

export const USERNAME_TAKEN_HINT: FieldHint = {
  ru: "Этот никнейм уже занят",
  kz: "Бұл никнейм бос емес",
};

export const USERNAME_CHECK_FAILED_HINT: FieldHint = {
  ru: "Не удалось проверить никнейм, попробуйте ещё раз",
  kz: "Никнеймді тексеру мүмкін болмады, қайта көріңіз",
};

export function checkUsername(username: string): { ok: true } | { ok: false; hint: FieldHint } {
  const u = username.trim();
  if (!u) {
    return { ok: false, hint: { ru: "Введите никнейм", kz: "Никнеймді енгізіңіз" } };
  }
  if (u.length < 3 || u.length > 25) {
    return {
      ok: false,
      hint: {
        ru: "Никнейм: от 3 до 25 символов",
        kz: "Никнейм: 3-тен 25 таңбаға дейін",
      },
    };
  }
  if (!/^[A-Za-z0-9_]+$/.test(u)) {
    return {
      ok: false,
      hint: {
        ru: "Никнейм: только латинские буквы, цифры и знак _",
        kz: "Никнейм: тек латын әріптері, сандар және _ таңбасы",
      },
    };
  }
  return { ok: true };
}

export function checkPassword(password: string): { ok: true } | { ok: false; hint: FieldHint } {
  if (password.length < 6) {
    return {
      ok: false,
      hint: { ru: "Пароль: не менее 6 символов", kz: "Құпиясөз: кемінде 6 таңба" },
    };
  }
  return { ok: true };
}

export function checkPasswordConfirm(
  password: string,
  confirm: string,
): { ok: true } | { ok: false; hint: FieldHint } {
  if (password !== confirm) {
    return {
      ok: false,
      hint: { ru: "Пароли должны совпадать", kz: "Құпиясөздер сәйкес келуі керек" },
    };
  }
  return { ok: true };
}

export function checkFullName(fullName: string): { ok: true } | { ok: false; hint: FieldHint } {
  if (!fullName.trim()) {
    return { ok: false, hint: { ru: "Введите имя и фамилию", kz: "Аты-жөніңізді енгізіңіз" } };
  }
  return { ok: true };
}

export function checkDirection(direction: string): { ok: true } | { ok: false; hint: FieldHint } {
  if (!direction.trim()) {
    return { ok: false, hint: { ru: "Укажите направление обучения", kz: "Оқу бағытын көрсетіңіз" } };
  }
  return { ok: true };
}

/** Значение направления из списка или поля «Другое» */
export function resolveDirectionOrOther(preset: string, other: string, otherSentinel: string): string {
  if (preset === otherSentinel) return other.trim();
  return preset.trim();
}

/** Значение предмета из списка или поля «Другое» */
export function resolveSubjectOrOther(preset: string, other: string, otherSentinel: string): string {
  if (preset === otherSentinel) return other.trim();
  return preset.trim();
}

export function checkInstitution(name: string): { ok: true } | { ok: false; hint: FieldHint } {
  if (!name.trim()) {
    return { ok: false, hint: { ru: "Укажите учебное учреждение", kz: "Оқу орнын көрсетіңіз" } };
  }
  return { ok: true };
}

export type RegisterDetailsParams = {
  acceptedTerms: boolean;
  email: string;
  fullName: string;
  username: string;
  password: string;
  role: "student" | "teacher";
  direction: string;
  institutionName: string;
};

/** Сводная проверка перед отправкой кода / регистрацией */
export function checkVerificationCode(
  code: string,
): { ok: true } | { ok: false; hint: FieldHint } {
  const n = code.replace(/\s+/g, "").trim();
  if (!n) {
    return { ok: false, hint: { ru: "Введите код из письма", kz: "Поштадағы кодты енгізіңіз" } };
  }
  if (!/^\d{6}$/.test(n)) {
    return {
      ok: false,
      hint: {
        ru: "Введите 6-значный код из письма",
        kz: "Поштадан келген 6 таңбалы кодты енгізіңіз",
      },
    };
  }
  return { ok: true };
}

export function validateRegisterDetails(params: RegisterDetailsParams): FieldHint | null {
  if (!params.acceptedTerms) {
    return {
      ru: "Примите пользовательское соглашение, чтобы продолжить регистрацию",
      kz: "Тіркелуді жалғастыру үшін пайдаланушы келісімін қабылдаңыз",
    };
  }
  const e = checkEmail(params.email);
  if (!e.ok) return e.hint;
  const fn = checkFullName(params.fullName);
  if (!fn.ok) return fn.hint;
  const u = checkUsername(params.username);
  if (!u.ok) return u.hint;
  if (params.role === "teacher") {
    const inst = checkInstitution(params.institutionName);
    if (!inst.ok) return inst.hint;
  }
  if (params.role === "student") {
    const d = checkDirection(params.direction);
    if (!d.ok) return d.hint;
  }
  const p = checkPassword(params.password);
  if (!p.ok) return p.hint;
  return null;
}
