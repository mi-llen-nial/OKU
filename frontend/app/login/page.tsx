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
  const [email, setEmail] = useState("student1@oku.local");
  const [password, setPassword] = useState("student123");
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
      setError(err instanceof Error ? err.message : "Login error");
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
            Email
            <input onChange={(e) => setEmail(e.target.value)} type="email" value={email} />
          </label>

          <label>
            Password
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
        <p className="authText" style={{ marginTop: 10 }}>
          Demo teacher: <b>teacher@oku.local / teacher123</b>
        </p>
      </div>
    </div>
  );
}
