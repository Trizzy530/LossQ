export async function POST(request: Request) {
  try {
    const formData = await request.formData();

    const backendResponse = await fetch("http://127.0.0.1:8000/upload/loss-run", {
      method: "POST",
      body: formData,
    });

    const text = await backendResponse.text();

    return new Response(text, {
      status: backendResponse.status,
      headers: {
        "Content-Type": backendResponse.headers.get("content-type") || "application/json",
      },
    });
  } catch (error: any) {
    return Response.json(
      {
        error: "Proxy upload failed",
        detail: error.message,
      },
      { status: 500 }
    );
  }
}