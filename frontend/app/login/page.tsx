"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import Button from "@/components/ui/Button";
import { login } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { assetPaths } from "@/src/assets";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await login({ email, password });
      saveSession(response);
      router.push(response.user.role === "teacher" ? "/teacher" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось выполнить вход");
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
            <h2 className="authTitle">Вход в OKU</h2>
            <p className="authText">Используйте аккаунт студента или преподавателя.</p>
          </div>
        </div>

        <form className="formGrid" onSubmit={handleSubmit}>
          <label>
            Почта
            <input onChange={(e) => setEmail(e.target.value)} type="email" value={email} />
          </label>

          <label>
            Пароль
            <input onChange={(e) => setPassword(e.target.value)} type="password" value={password} />
          </label>

          {error && <div className="errorText">{error}</div>}

          <Button block disabled={loading} type="submit">
            {loading ? "Выполняем вход..." : "Войти"}
          </Button>
        </form>

        <p className="authText" style={{ marginTop: 14 }}>
          Нет аккаунта? <Link href="/register">Регистрация</Link>
        </p>
      </div>
    </div>
  );
}
