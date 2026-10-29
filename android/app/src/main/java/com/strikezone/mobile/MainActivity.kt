package com.strikezone.mobile

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            text = "스트존\n개발 환경 확인용 앱\n촬영·통신·판정 기능은 준비 중입니다."
            textSize = 22f
            val padding = (24 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding, padding, padding)
        })
    }
}
