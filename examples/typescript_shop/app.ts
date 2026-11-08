import express from "express";
import { validateOrder } from "./validators.ts";

export function createApp() {
  const app = express();
  app.get("/orders/:quantity", function orderRoute(request, response) {
    const quantity = Number(request.params.quantity);
    if (!validateOrder(quantity)) {
      response.status(400).json({ error: "Invalid quantity" });
      return;
    }
    response.json({ quantity });
  });
  return app;
}
