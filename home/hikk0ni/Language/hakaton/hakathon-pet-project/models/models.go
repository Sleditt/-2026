package models

import (
	"github.com/golang-jwt/jwt/v5"
)

// --- МОДЕЛИ БАЗЫ ДАННЫХ ---
type Auth struct {
	ID       uint   `gorm:"primaryKey"`
	Email    string `gorm:"unique;not null"`
	Password string `gorm:"not null"`
	Role     string `gorm:"not null"` // "student"
}

type User struct {
	ID      uint   `gorm:"primaryKey" json:"id"`
	AuthID  uint   `json:"auth_id"`
	Name    string `json:"name"`
	Surname string `json:"surname"`

	// --- НОВЫЕ ПОЛЯ ДЛЯ ГЕЙМИФИКАЦИИ ---
	Score       int    `gorm:"default:0" json:"score"`
	LearnedIDs  string `gorm:"default:''" json:"learned_ids"`
	MasteredIDs string `gorm:"default:''" json:"mastered_ids"`
	MistakesIDs string `gorm:"default:''" json:"mistakes_ids"`
}

type Task struct {
	ID          uint   `gorm:"primaryKey" json:"fragment_id"`
	TextBa      string `json:"text_ba"`
	Translation string `json:"translation"`
	CorrectHint string `json:"correct_hint"`
}

// --- DTO ДЛЯ ВХОДЯЩИХ ЗАПРОСОВ ---
type RequestRegister struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=6"`
	Name     string `json:"name" binding:"required"`
	Surname  string `json:"surname" binding:"required"`
}

type RequestAuth struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=6"`
}

type RequestSubmitTask struct {
	FragmentID  uint   `json:"fragment_id" binding:"required"`
	Translation string `json:"translation" binding:"required"`
}

// --- СТРУКТУРЫ JWT-ТОКЕНОВ ТИМЛИДА (НЕ ТРОГАЕМ) ---
type TokenDataTransfer struct {
	AccessToken    string
	RefreshToken   string
	RefreshTokenID string
	AtExpires      int64
	RtExpires      int64
}

type AccessTokenData struct {
	AuthID uint   `json:"AuthID"`
	Role   string `json:"Role"`
	jwt.RegisteredClaims
}

type RefreshTokenData struct {
	RtID   string `json:"RtID"`
	AuthID uint   `json:"AuthID"`
	jwt.RegisteredClaims
}

type RefreshToken struct {
	RefreshToken string `json:"RefreshToken"`
}
