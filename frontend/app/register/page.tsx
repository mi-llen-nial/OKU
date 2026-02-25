"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import Button from "@/components/ui/Button";
import { register } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { Language, UserRole } from "@/lib/types";
import { assetPaths } from "@/src/assets";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("student");
  const [language, setLanguage] = useState<Language>("RU");
  const [groupId, setGroupId] = useState("1");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const payload = await register({
        email,
        username,
        password,
        role,
        preferred_language: language,
        group_id: role === "student" ? Number(groupId) : null,
      });
      saveSession(payload);
      router.push(role === "teacher" ? "/teacher" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration error");
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
            Email
            <input onChange={(e) => setEmail(e.target.value)} required type="email" value={email} />
          </label>

          <label>
            Username
            <input onChange={(e) => setUsername(e.target.value)} required value={username} />
          </label>

          <label>
            Password
            <input
              minLength={6}
              onChange={(e) => setPassword(e.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          <label>
            Role
            <select onChange={(e) => setRole(e.target.value as UserRole)} value={role}>
              <option value="student">student</option>
              <option value="teacher">teacher</option>
            </select>
          </label>

          <label>
            Preferred language
            <select onChange={(e) => setLanguage(e.target.value as Language)} value={language}>
              <option value="RU">RU</option>
              <option value="KZ">KZ</option>
            </select>
          </label>

          {role === "student" && (
            <label>
              Group ID
              <input onChange={(e) => setGroupId(e.target.value)} type="number" value={groupId} />
            </label>
          )}

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
