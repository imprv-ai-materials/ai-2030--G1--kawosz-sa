// Przeliczenie kalkulatora po zmianie suwaka: przeglądarka pyta Next.js, a ten API (bez CORS, adres API zostaje
// po stronie serwera, jak w pozostałych stronach).

const API = process.env.KAWOSZ_API ?? "http://127.0.0.1:8101";

export async function GET(request: Request) {
  const { search } = new URL(request.url);
  try {
    const odpowiedz = await fetch(`${API}/api/wizyty${search}`, { cache: "no-store", signal: request.signal });
    return new Response(odpowiedz.body, {
      status: odpowiedz.status,
      headers: { "content-type": odpowiedz.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: `Brak połączenia z API pod adresem ${API}.` }, { status: 502 });
  }
}
