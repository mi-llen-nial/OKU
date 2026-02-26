"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import Button from "@/components/ui/Button";
import { register } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { EducationLevel, UserRole } from "@/lib/types";
import { assetPaths } from "@/src/assets";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<UserRole>("student");
  const [educationLevel, setEducationLevel] = useState<EducationLevel>("school");
  const [direction, setDirection] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    const usernameValue = username.trim();
    if (!/^[A-Za-z0-9_]{3,25}$/.test(usernameValue)) {
      setLoading(false);
      setError("Имя пользователя: только латинские буквы, цифры и _, длина 3-25 символов.");
      return;
    }

    try {
      const payload = await register({
        email,
        full_name: fullName,
        username: usernameValue,
        education_level: role === "student" ? educationLevel : undefined,
        direction: role === "student" ? direction.trim() : undefined,
        password,
        role,
        preferred_language: "RU",
      });
      saveSession(payload);
      router.push(payload.user.role === "teacher" ? "/teacher" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать аккаунт");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="authPage">
      <div className="authCard">
        <div className="authHeader">
          <img className="authLogo" src={assetPaths.logo.png} alt="OKU" />
          <div>
            <h2 className="authTitle">Регистрация в OKU</h2>
            <p className="authText">Создайте профиль и начните обучение.</p>
          </div>
        </div>

        <form className="formGrid" onSubmit={handleSubmit}>
          <label>
            Почта
            <input onChange={(e) => setEmail(e.target.value)} required type="email" value={email} />
          </label>

          <label>
            Имя и фамилия
            <input onChange={(e) => setFullName(e.target.value)} required value={fullName} />
          </label>

          <label>
            Имя пользователя
            <input
              maxLength={25}
              onChange={(e) => setUsername(e.target.value)}
              pattern="[A-Za-z0-9_]{3,25}"
              required
              title="Только латинские буквы, цифры и _, длина 3-25 символов"
              value={username}
            />
          </label>

          <label>
            Роль
            <select onChange={(e) => setRole(e.target.value as UserRole)} value={role}>
              <option value="student">Студент</option>
              <option value="teacher">Преподаватель (админ)</option>
            </select>
          </label>

          {role === "student" && (
            <label>
              Статус обучения
              <select onChange={(e) => setEducationLevel(e.target.value as EducationLevel)} value={educationLevel}>
                <option value="school">Школьник</option>
                <option value="college">Студент колледжа</option>
                <option value="university">Студент университета</option>
              </select>
            </label>
          )}

          {role === "student" && (
            <label>
              Направление
              <input onChange={(e) => setDirection(e.target.value)} placeholder="Например: ИТ, медицина, экономика" required value={direction} />
            </label>
          )}

          <label>
            Пароль
            <input
              minLength={6}
              onChange={(e) => setPassword(e.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          {error && <div className="errorText">{error}</div>}

          <Button block disabled={loading} type="submit">
            {loading ? "Создаём профиль..." : "Зарегистрироваться"}
          </Button>
        </form>

        <p className="authText" style={{ marginTop: 14 }}>
          Уже есть аккаунт? <Link href="/login">Войти</Link>
        </p>
      </div>
    </div>
  );
}
