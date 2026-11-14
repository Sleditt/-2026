package main

import (
	"log"

	"hakathon/handlers"
	"hakathon/middleware"

	// "hakathon/redis" // Отключили Redis для хакатона, чтобы сервер не падал на Windows
	"hakathon/repository"

	"github.com/gin-gonic/gin"
)

func main() {
	// redis.InitRedis() // Отключено
	repository.Initdb()

	r := gin.Default()
	r.Use(middleware.CORS())

	// Публичные маршруты (доступны боту и сайту)
	public := r.Group("/api")
	{
		// Аутентификация
		public.POST("/login", handlers.Login)
		public.POST("/register", handlers.Register)

		// Задания
		public.GET("/task/daily", handlers.GetDailyTask)
		public.GET("/task/:id", handlers.GetTaskByID)

		// --- НОВЫЕ МАРШРУТЫ СИНХРОНИЗАЦИИ И ИНТЕРФЕЙСА ---
		public.GET("/sync", handlers.PullSync)
		public.POST("/sync", handlers.PushSync)

		public.GET("/profile", handlers.GetProfile)
		public.GET("/rating", handlers.GetRating)
		public.GET("/dictionary", handlers.GetDictionary)
	}

	// Приватные маршруты (сейчас пустые, так как мы всё открыли для хакатона)
	private := r.Group("/api")
	private.Use(middleware.AuthRequired())
	{
	}

	log.Println("🚀 Образовательный сервер BASHWORD запущен на порту 8080...")
	r.Run(":8080")
}
